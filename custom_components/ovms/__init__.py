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
    CONF_CONFIG_ENTRY_ID,
    CONF_TOPIC_STRUCTURE,
    CONF_TOPIC_BLACKLIST,
    get_platforms_loaded_signal,
)

from .mqtt import OVMSMQTTClient
from .migrations import (
    async_cleanup_stale_device_associations,
    async_migrate_entity_identity,
    async_migrate_entity_naming,
    async_migrate_lock_entities,
)
from .services import async_setup_services, async_unload_services
from .utils import (
    generate_ovms_client_id,
    get_merged_config,
    sanitize_topic_structure,
)

_LOGGER = logging.getLogger(LOGGER_NAME)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.LOCK,
    Platform.DEVICE_TRACKER,
]


async def _sanitize_persisted_topic_structure(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Strip whitespace from persisted topic_structure in data and options."""
    updated_data = None
    updated_options = None

    raw_data = entry.data.get(CONF_TOPIC_STRUCTURE)
    clean_data = sanitize_topic_structure(raw_data)
    if clean_data and clean_data != raw_data:
        updated_data = {**entry.data, CONF_TOPIC_STRUCTURE: clean_data}
        _LOGGER.info(
            "Stripped whitespace from stored topic_structure in data: %r -> %r",
            raw_data,
            clean_data,
        )

    raw_options = entry.options.get(CONF_TOPIC_STRUCTURE)
    clean_options = sanitize_topic_structure(raw_options)
    if clean_options and clean_options != raw_options:
        updated_options = {**entry.options, CONF_TOPIC_STRUCTURE: clean_options}
        _LOGGER.info(
            "Stripped whitespace from stored topic_structure in options: %r -> %r",
            raw_options,
            clean_options,
        )

    if updated_data is not None or updated_options is not None:
        hass.config_entries.async_update_entry(
            entry,
            data=updated_data or entry.data,
            options=updated_options or entry.options,
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OVMS from a config entry."""
    _LOGGER.info("Setting up OVMS integration")

    hass.data.setdefault(DOMAIN, {})

    try:
        # Always check for missing client_id (critical for MQTT stability)
        client_id_changed = await _migrate_client_id(hass, entry, entry.version)

        # Check if we need to migrate the config entry
        migrated = entry.version < CONFIG_VERSION
        if migrated:
            _LOGGER.info(
                "Migrating config entry from version %s to %s",
                entry.version,
                CONFIG_VERSION,
            )
            if not await async_migrate_entry(hass, entry):
                _LOGGER.error(
                    "Failed to migrate OVMS config entry %s; aborting setup",
                    entry.entry_id,
                )
                return False

        # Fix persisted topic_structure with leading/trailing whitespace
        # (observed in issue #199 from config flow saving with a leading space)
        await _sanitize_persisted_topic_structure(hass, entry)

        if client_id_changed and not migrated:
            await async_migrate_entity_identity(hass, entry, entry.version)

        # Remove stale device associations only after a migration just ran.
        # Also run after a current-version entry gains a stable client_id,
        # because device_info will switch from vehicle_id to client_id.
        if migrated or client_id_changed:
            await async_cleanup_stale_device_associations(hass, entry)

        # Merge entry.data with entry.options, giving priority to options
        config = get_merged_config(entry)
        config[CONF_CONFIG_ENTRY_ID] = entry.entry_id

        # Debug: Check if client_id is present in the merged config
        from .const import CONF_CLIENT_ID

        _LOGGER.debug(
            "Setup: entry.data has client_id: %s", CONF_CLIENT_ID in entry.data
        )
        _LOGGER.debug(
            "Setup: entry.options has client_id: %s",
            CONF_CLIENT_ID in entry.options if entry.options else False,
        )
        _LOGGER.debug(
            "Setup: merged config has client_id: %s", CONF_CLIENT_ID in config
        )
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
        async_dispatcher_send(hass, get_platforms_loaded_signal(entry.entry_id))

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


async def _migrate_blacklist_patterns(
    hass: HomeAssistant, config_entry: ConfigEntry, from_version: int
) -> None:
    """Migrate blacklist patterns from legacy format to current format."""
    from .const import (
        COMBINED_TOPIC_BLACKLIST,
        SYSTEM_TOPIC_BLACKLIST,
        LEGACY_TOPIC_BLACKLIST,
    )

    current_data = dict(config_entry.data)
    current_options = dict(config_entry.options)

    # Get existing blacklist
    existing_blacklist = current_options.get(
        CONF_TOPIC_BLACKLIST, current_data.get(CONF_TOPIC_BLACKLIST, [])
    )

    if not existing_blacklist:
        # New user - populate with system defaults
        current_options[CONF_TOPIC_BLACKLIST] = SYSTEM_TOPIC_BLACKLIST[
            :
        ]  # Copy to avoid reference issues
        hass.config_entries.async_update_entry(config_entry, options=current_options)
        _LOGGER.info(
            "V%d Migration: Initial setup - populated blacklist with system defaults",
            from_version,
        )
        return

    # Existing user - smart migration that separates user patterns from system patterns
    # Identify truly custom user patterns (not in any system list)
    user_only_patterns = [
        pattern
        for pattern in existing_blacklist
        if pattern not in COMBINED_TOPIC_BLACKLIST
    ]

    # For migration, we want: current system patterns + user-only patterns
    # This replaces legacy system patterns with current ones while preserving user customizations
    updated_blacklist = (
        SYSTEM_TOPIC_BLACKLIST[:] + user_only_patterns
    )  # Start with current system patterns
    updated_blacklist = list(dict.fromkeys(updated_blacklist))  # Remove any duplicates

    # Check if update is needed: always update from v2, otherwise only if the list actually changed
    should_update = (from_version == 2) or (updated_blacklist != existing_blacklist)

    if should_update:
        current_options[CONF_TOPIC_BLACKLIST] = updated_blacklist
        hass.config_entries.async_update_entry(config_entry, options=current_options)

        # Log what changed
        removed_legacy = [p for p in existing_blacklist if p in LEGACY_TOPIC_BLACKLIST]
        added_current = [
            p for p in SYSTEM_TOPIC_BLACKLIST if p not in existing_blacklist
        ]

        _LOGGER.info("V%d Migration: Cleaned up blacklist patterns", from_version)
        if removed_legacy:
            _LOGGER.info(
                "V%d Migration: removed %d legacy patterns: %s",
                from_version,
                len(removed_legacy),
                removed_legacy,
            )
        if added_current:
            _LOGGER.info(
                "V%d Migration: added %d current system patterns: %s",
                from_version,
                len(added_current),
                added_current,
            )
        if user_only_patterns:
            _LOGGER.info(
                "V%d Migration: preserved %d user patterns: %s",
                from_version,
                len(user_only_patterns),
                user_only_patterns,
            )


async def _migrate_client_id(
    hass: HomeAssistant, config_entry: ConfigEntry, from_version: int
) -> bool:
    """Generate and store stable MQTT client ID for existing installations."""
    from .const import CONF_CLIENT_ID

    current_data = dict(config_entry.data)

    expected_client_id = generate_ovms_client_id(current_data)
    current_client_id = current_data.get(CONF_CLIENT_ID)

    if current_client_id == expected_client_id:
        _LOGGER.debug(
            "V%d Migration: Client ID already up to date: %s",
            from_version,
            current_client_id,
        )
        return False

    _LOGGER.info(
        "V%d Migration: Updating stable MQTT client ID to %s",
        from_version,
        expected_client_id,
    )

    # Update the config entry data
    current_data[CONF_CLIENT_ID] = expected_client_id
    hass.config_entries.async_update_entry(config_entry, data=current_data)

    _LOGGER.info(
        "V%d Migration: Generated stable MQTT client ID: %s",
        from_version,
        expected_client_id,
    )
    _LOGGER.debug(
        "V%d Migration: Updated config entry data with client_id", from_version
    )
    return True


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate an old config entry to new version."""
    try:
        version = config_entry.version

        # Always check for missing client_id regardless of version
        await _migrate_client_id(hass, config_entry, version)

        # If the config entry is already up-to-date, return True
        if version == CONFIG_VERSION:
            return True

        _LOGGER.debug(
            "Migrating config entry from version %s to %s", version, CONFIG_VERSION
        )

        # Perform migrations based on version
        if version in [1, 2, 3, 4]:
            # Migrate blacklist patterns to clean format
            await _migrate_blacklist_patterns(hass, config_entry, version)

        if version <= 3:
            await async_migrate_lock_entities(hass, config_entry, version)

        if version <= 4:
            await async_migrate_entity_identity(hass, config_entry, version)

        if version <= 5:
            await async_migrate_entity_naming(hass, config_entry, version)

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
