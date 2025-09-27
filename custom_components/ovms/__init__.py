"""The OVMS integration."""
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    DOMAIN,
    LOGGER_NAME,
    CONFIG_VERSION,
    SIGNAL_PLATFORMS_LOADED,
    CONF_TOPIC_BLACKLIST
)

from .mqtt import OVMSMQTTClient
from .services import async_setup_services, async_unload_services
from .utils import get_merged_config

_LOGGER = logging.getLogger(LOGGER_NAME)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.DEVICE_TRACKER,
]


def _get_merged_config(entry: ConfigEntry) -> dict:
    """Get merged configuration from entry.data and entry.options.

    Options take precedence over data.
    """
    return get_merged_config(entry)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OVMS from a config entry."""
    _LOGGER.info("Setting up OVMS integration")

    hass.data.setdefault(DOMAIN, {})

    try:
        # Always check for missing client_id (critical for MQTT stability)
        await _migrate_client_id(hass, entry, entry.version)
        
        # Check if we need to migrate the config entry
        if entry.version < CONFIG_VERSION:
            _LOGGER.info("Migrating config entry from version %s to %s", entry.version, CONFIG_VERSION)
            await async_migrate_entry(hass, entry)

        # Merge entry.data with entry.options, giving priority to options
        config = _get_merged_config(entry)
        
        # Debug: Check if client_id is present in the merged config
        from .const import CONF_CLIENT_ID
        _LOGGER.debug("Setup: entry.data has client_id: %s", CONF_CLIENT_ID in entry.data)
        _LOGGER.debug("Setup: entry.options has client_id: %s", CONF_CLIENT_ID in entry.options if entry.options else False)
        _LOGGER.debug("Setup: merged config has client_id: %s", CONF_CLIENT_ID in config)
        if CONF_CLIENT_ID in config:
            _LOGGER.debug("Setup: client_id value: %s", config[CONF_CLIENT_ID])

        # Create MQTT client
        mqtt_client = OVMSMQTTClient(hass, config)

        # Set up the MQTT client
        if not await mqtt_client.async_setup():
            _LOGGER.error("Failed to set up MQTT client")
            return False

        # Store the client in hass.data
        hass.data[DOMAIN][entry.entry_id] = {
            "mqtt_client": mqtt_client,
        }

        # Set up platforms
        _LOGGER.debug("Setting up platforms: %s", PLATFORMS)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        # Set up services
        await async_setup_services(hass)

        # Update listener for config entry changes
        entry.async_on_unload(entry.add_update_listener(async_update_options))

        # Signal that all platforms are loaded
        _LOGGER.info("All platforms loaded, notifying MQTT client")
        async_dispatcher_send(hass, SIGNAL_PLATFORMS_LOADED)

        return True
    except Exception as ex:
        _LOGGER.exception("Error setting up OVMS integration: %s", ex)

        # Clean up any partial setup
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            if "mqtt_client" in hass.data[DOMAIN][entry.entry_id]:
                mqtt_client = hass.data[DOMAIN][entry.entry_id]["mqtt_client"]
                await mqtt_client.async_shutdown()
            hass.data[DOMAIN].pop(entry.entry_id, None)

        return False


async def _migrate_blacklist_patterns(hass: HomeAssistant, config_entry: ConfigEntry, from_version: int) -> None:
    """Migrate blacklist patterns from legacy format to current format."""
    from .const import COMBINED_TOPIC_BLACKLIST, SYSTEM_TOPIC_BLACKLIST, LEGACY_TOPIC_BLACKLIST
    
    current_data = dict(config_entry.data)
    current_options = dict(config_entry.options)
    
    # Get existing blacklist
    existing_blacklist = current_options.get(CONF_TOPIC_BLACKLIST, current_data.get(CONF_TOPIC_BLACKLIST, []))
    
    if not existing_blacklist:
        # New user - populate with system defaults 
        current_options[CONF_TOPIC_BLACKLIST] = SYSTEM_TOPIC_BLACKLIST[:]  # Copy to avoid reference issues
        hass.config_entries.async_update_entry(config_entry, options=current_options)
        _LOGGER.info("V%d Migration: Initial setup - populated blacklist with system defaults", from_version)
        return
    
    # Existing user - smart migration that separates user patterns from system patterns
    # Identify truly custom user patterns (not in any system list)
    user_only_patterns = [pattern for pattern in existing_blacklist if pattern not in COMBINED_TOPIC_BLACKLIST]
    
    # For migration, we want: current system patterns + user-only patterns
    # This replaces legacy system patterns with current ones while preserving user customizations
    updated_blacklist = SYSTEM_TOPIC_BLACKLIST[:] + user_only_patterns  # Start with current system patterns
    updated_blacklist = list(dict.fromkeys(updated_blacklist))  # Remove any duplicates
    
    # Check if update is needed (for version 1->2, only update if changed; for version 2->3, always update)
    should_update = (from_version == 2) or (updated_blacklist != existing_blacklist)
    
    if should_update:
        current_options[CONF_TOPIC_BLACKLIST] = updated_blacklist
        hass.config_entries.async_update_entry(config_entry, options=current_options)
        
        # Log what changed
        removed_legacy = [p for p in existing_blacklist if p in LEGACY_TOPIC_BLACKLIST]
        added_current = [p for p in SYSTEM_TOPIC_BLACKLIST if p not in existing_blacklist]
        
        _LOGGER.info("V%d Migration: Cleaned up blacklist patterns", from_version)
        if removed_legacy:
            _LOGGER.info("V%d Migration: removed %d legacy patterns: %s", from_version, len(removed_legacy), removed_legacy)
        if added_current:
            _LOGGER.info("V%d Migration: added %d current system patterns: %s", from_version, len(added_current), added_current)
        if user_only_patterns:
            _LOGGER.info("V%d Migration: preserved %d user patterns: %s", from_version, len(user_only_patterns), user_only_patterns)


async def _migrate_client_id(hass: HomeAssistant, config_entry: ConfigEntry, from_version: int) -> None:
    """Generate and store stable MQTT client ID for existing installations."""
    import hashlib
    from .const import CONF_CLIENT_ID, CONF_VEHICLE_ID
    
    current_data = dict(config_entry.data)
    
    # Check if client_id already exists
    if CONF_CLIENT_ID in current_data and current_data[CONF_CLIENT_ID]:
        _LOGGER.debug("V%d Migration: Client ID already exists: %s", from_version, current_data[CONF_CLIENT_ID])
        return
    
    _LOGGER.info("V%d Migration: Client ID missing, generating new stable client ID", from_version)
    
    # Generate stable client ID including username to prevent collisions
    # Multiple users can have same vehicle_id, but username must be unique on broker
    from homeassistant.const import CONF_USERNAME
    host = current_data.get(CONF_HOST, "unknown")
    username = current_data.get(CONF_USERNAME, "unknown")
    vehicle_id = current_data.get(CONF_VEHICLE_ID, "unknown")
    
    # Debug logging to understand what values we're working with
    _LOGGER.debug("V%d Migration: Raw config values - host: %s, username: %s, vehicle_id: %s", 
                  from_version, repr(host), repr(username), repr(vehicle_id))
    
    client_id_base = f"{host}_{username}_{vehicle_id}"
    client_id = f"ha_ovms_{hashlib.sha256(client_id_base.encode()).hexdigest()[:12]}"
    
    # Debug: Log the hash input and output
    _LOGGER.debug("V%d Migration: Hash input: %s", from_version, repr(client_id_base))
    _LOGGER.debug("V%d Migration: Generated hash: %s", from_version, hashlib.sha256(client_id_base.encode()).hexdigest()[:12])
    
    # Update the config entry data
    current_data[CONF_CLIENT_ID] = client_id
    hass.config_entries.async_update_entry(config_entry, data=current_data)
    
    _LOGGER.info("V%d Migration: Generated stable MQTT client ID: %s", from_version, client_id)
    _LOGGER.debug("V%d Migration: Updated config entry data with client_id", from_version)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate an old config entry to new version."""
    try:
        version = config_entry.version

        # Always check for missing client_id regardless of version
        await _migrate_client_id(hass, config_entry, version)

        # If the config entry is already up-to-date, return True
        if version == CONFIG_VERSION:
            return True

        _LOGGER.debug("Migrating config entry from version %s to %s", version, CONFIG_VERSION)

        # Perform migrations based on version
        if version in [1, 2]:
            # Migrate blacklist patterns to clean format
            await _migrate_blacklist_patterns(hass, config_entry, version)

        # Update the config entry version
        hass.config_entries.async_update_entry(config_entry, version=CONFIG_VERSION)
        return True
    except Exception as ex:
        _LOGGER.exception("Error migrating config entry: %s", ex)
        return False


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    try:
        await hass.config_entries.async_reload(entry.entry_id)
    except Exception as ex:
        _LOGGER.exception("Error updating options: %s", ex)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading OVMS integration")

    try:
        # Check if the entry exists in hass.data
        if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]:
            _LOGGER.warning("Trying to unload an entry that is not loaded")
            return True

        # Unload platforms
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

        if unload_ok:
            # Shut down MQTT client
            mqtt_client = hass.data[DOMAIN][entry.entry_id]["mqtt_client"]
            await mqtt_client.async_shutdown()

            # Remove config entry from hass.data
            hass.data[DOMAIN].pop(entry.entry_id)

            # Unload services if this is the last config entry
            if len(hass.data[DOMAIN]) == 0:
                await async_unload_services(hass)

        return unload_ok
    except Exception as ex:
        _LOGGER.exception("Error unloading entry: %s", ex)

        # Try to clean up as much as possible
        try:
            if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
                if "mqtt_client" in hass.data[DOMAIN][entry.entry_id]:
                    mqtt_client = hass.data[DOMAIN][entry.entry_id]["mqtt_client"]
                    await mqtt_client.async_shutdown()
                hass.data[DOMAIN].pop(entry.entry_id, None)

                # Unload services if this is the last config entry
                if len(hass.data[DOMAIN]) == 0:
                    await async_unload_services(hass)
        except Exception as ex2:
            _LOGGER.exception("Error during cleanup after failed unload: %s", ex2)

        return False
