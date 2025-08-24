"""The OVMS integration."""
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
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
        # Check if we need to migrate the config entry
        if entry.version < CONFIG_VERSION:
            _LOGGER.info("Migrating config entry from version %s to %s", entry.version, CONFIG_VERSION)
            await async_migrate_entry(hass, entry)

        # Merge entry.data with entry.options, giving priority to options
        config = _get_merged_config(entry)

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


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate an old config entry to new version."""
    try:
        version = config_entry.version

        # If the config entry is already up-to-date, return True
        if version == CONFIG_VERSION:
            return True

        _LOGGER.debug("Migrating config entry from version %s to %s", version, CONFIG_VERSION)

        # Perform migrations based on version
        if version == 1:
            # Migrate blacklist: separate user patterns from system patterns
            current_data = dict(config_entry.data)
            current_options = dict(config_entry.options)
            
            # Get existing blacklist (mix of system + user patterns)
            existing_blacklist = current_options.get(CONF_TOPIC_BLACKLIST, current_data.get(CONF_TOPIC_BLACKLIST, []))
            
            # Extract only user-added patterns (remove system patterns)
            from .const import SYSTEM_TOPIC_BLACKLIST
            user_only_patterns = [pattern for pattern in existing_blacklist if pattern not in SYSTEM_TOPIC_BLACKLIST]
            
            # Update to store only user patterns (system patterns will be applied automatically)
            if user_only_patterns != existing_blacklist:
                current_options[CONF_TOPIC_BLACKLIST] = user_only_patterns
                hass.config_entries.async_update_entry(config_entry, options=current_options)
                _LOGGER.info("Migrated blacklist: separated %d user patterns from system patterns", len(user_only_patterns))

        # Update the config entry version
        hass.config_entries.async_update_entry(config_entry, version=CONFIG_VERSION)
        return True
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
