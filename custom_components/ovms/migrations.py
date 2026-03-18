"""Config-entry migration helpers for the OVMS integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers import device_registry, entity_registry

from .const import (
    CONF_CLIENT_ID,
    CONF_VEHICLE_ID,
    DOMAIN,
    LOCATION_ENTITY_NAME,
    LOGGER_NAME,
    OVMS_DEVICE_MANUFACTURER,
    OVMS_DEVICE_MODEL,
    STATUS_ENTITY_NAME,
    STALENESS_STATUS_ENTITY_NAME,
    STALENESS_UNIQUE_ID_MARKER,
)
from .utils import (
    get_merged_config,
    get_namespaced_ovms_unique_id,
    get_ovms_device_name,
    get_ovms_device_identifier,
)

_LOGGER = logging.getLogger(LOGGER_NAME)

_LEGACY_LOCK_METRIC_MARKER = "_v_e_locked_"
_SWITCH_SUFFIX = "_switch"
_LOCK_SUFFIX = "_lock"


def _get_entity_domain(entity_id: str) -> str:
    """Return the domain portion of an entity_id."""
    return entity_id.split(".", 1)[0]


def _generate_entity_id_from_name(domain: str, name: str, current_ids=None) -> str:
    """Generate an entity_id from a display name using HA's slug rules."""
    return async_generate_entity_id(
        f"{domain}.{{}}",
        name,
        current_ids=current_ids,
    )


def _strip_vehicle_prefix(name: str, vehicle_id: str) -> str:
    """Strip a leading vehicle_id prefix from an entity name when present."""
    if not name or not vehicle_id:
        return name

    prefix = f"{vehicle_id} "
    if name.lower().startswith(prefix.lower()):
        stripped = name[len(prefix) :].strip()
        if stripped:
            return stripped

    return name


def _get_desired_entity_name(
    registry_entry: entity_registry.RegistryEntry,
    vehicle_id: str,
) -> str | None:
    """Return the integration-managed entity name for registry migration."""
    if (
        isinstance(registry_entry.unique_id, str)
        and STALENESS_UNIQUE_ID_MARKER in registry_entry.unique_id
    ):
        return STALENESS_STATUS_ENTITY_NAME

    if registry_entry.domain == Platform.DEVICE_TRACKER:
        return LOCATION_ENTITY_NAME

    current_name = registry_entry.original_name or registry_entry.name
    if not current_name:
        return None

    desired_name = _strip_vehicle_prefix(current_name, vehicle_id)
    if desired_name.lower() == STATUS_ENTITY_NAME.lower():
        return STATUS_ENTITY_NAME

    if desired_name.lower() == LOCATION_ENTITY_NAME.lower():
        return LOCATION_ENTITY_NAME

    return desired_name


def _is_legacy_auto_entity_id(
    registry_entry: entity_registry.RegistryEntry,
    current_name: str | None,
) -> bool:
    """Return True when the entity_id still matches HA's old auto-generated form."""
    if not current_name:
        return False

    domain = _get_entity_domain(registry_entry.entity_id)
    legacy_entity_id = _generate_entity_id_from_name(domain, current_name, set())
    return registry_entry.entity_id == legacy_entity_id


def _is_legacy_lock_switch(entity_entry: entity_registry.RegistryEntry) -> bool:
    """Return True when an entity entry is the legacy OVMS lock switch."""
    return (
        entity_entry.domain == Platform.SWITCH
        and entity_entry.platform == DOMAIN
        and isinstance(entity_entry.unique_id, str)
        and entity_entry.unique_id.endswith(_SWITCH_SUFFIX)
        and _LEGACY_LOCK_METRIC_MARKER in entity_entry.unique_id
    )


def _build_lock_object_id(entity_id: str) -> str:
    """Derive the replacement lock object_id from a legacy switch entity_id."""
    object_id = entity_id.split(".", 1)[1]
    if object_id.endswith(_SWITCH_SUFFIX):
        return object_id[: -len(_SWITCH_SUFFIX)]

    return object_id


def _device_contains_only_config_entry_entities(
    registry: entity_registry.EntityRegistry,
    device_id: str,
    config_entry_id: str,
) -> bool:
    """Return True when a device only contains entities from one config entry."""
    return all(
        registry_entry.config_entry_id == config_entry_id
        for registry_entry in entity_registry.async_entries_for_device(
            registry,
            device_id,
            include_disabled_entities=True,
        )
    )


def _copy_device_customizations(
    device_reg: device_registry.DeviceRegistry,
    source_device: device_registry.DeviceEntry,
    target_device: device_registry.DeviceEntry,
) -> device_registry.DeviceEntry:
    """Copy user-managed device metadata onto a migrated device when missing."""
    update_kwargs = {}

    if source_device.area_id and not target_device.area_id:
        update_kwargs["area_id"] = source_device.area_id

    if source_device.name_by_user and not target_device.name_by_user:
        update_kwargs["name_by_user"] = source_device.name_by_user

    if not update_kwargs:
        return target_device

    return device_reg.async_update_device(target_device.id, **update_kwargs)


async def async_migrate_lock_entities(
    hass: HomeAssistant, config_entry: ConfigEntry, from_version: int
) -> None:
    """Migrate OVMS vehicle lock control from switch to native lock entities."""
    registry = entity_registry.async_get(hass)
    registry_entries = entity_registry.async_entries_for_config_entry(
        registry, config_entry.entry_id
    )

    for registry_entry in registry_entries:
        if not _is_legacy_lock_switch(registry_entry):
            continue

        old_entity_id = registry_entry.entity_id
        new_unique_id = (
            f"{registry_entry.unique_id[:-len(_SWITCH_SUFFIX)]}{_LOCK_SUFFIX}"
        )

        new_entry = registry.async_get_or_create(
            Platform.LOCK,
            DOMAIN,
            new_unique_id,
            config_entry=config_entry,
            device_id=registry_entry.device_id,
            suggested_object_id=_build_lock_object_id(old_entity_id),
            disabled_by=registry_entry.disabled_by,
            hidden_by=registry_entry.hidden_by,
            entity_category=registry_entry.entity_category,
            original_icon=registry_entry.original_icon,
            original_name=registry_entry.original_name,
        )

        registry.async_update_entity(
            new_entry.entity_id,
            area_id=registry_entry.area_id,
            aliases=registry_entry.aliases,
            icon=registry_entry.icon,
            labels=registry_entry.labels,
            name=registry_entry.name,
        )
        registry.async_remove(old_entity_id)

        _LOGGER.info(
            "V%d Migration: migrated lock control from %s to %s",
            from_version,
            old_entity_id,
            new_entry.entity_id,
        )


async def async_migrate_entity_identity(
    hass: HomeAssistant, config_entry: ConfigEntry, from_version: int
) -> None:
    """Namespace OVMS entity identities per config entry.

    Home Assistant permits the config entry ID as a last-resort entity unique ID.
    We use it as a stable namespace to prevent collisions between multiple OVMS
    entries that expose the same vehicle_id and metric paths.
    """
    config = get_merged_config(config_entry)
    vehicle_id = config.get(CONF_VEHICLE_ID, "unknown")
    client_id = config.get(CONF_CLIENT_ID)
    new_device_identifier = get_ovms_device_identifier(client_id, vehicle_id)

    entity_reg = entity_registry.async_get(hass)
    device_reg = device_registry.async_get(hass)
    registry_entries = entity_registry.async_entries_for_config_entry(
        entity_reg, config_entry.entry_id
    )

    if not registry_entries:
        return

    existing_device = None
    for registry_entry in registry_entries:
        if registry_entry.device_id:
            existing_device = device_reg.async_get(registry_entry.device_id)
            if existing_device:
                break

    if not existing_device and vehicle_id:
        existing_device = device_reg.async_get_device(
            identifiers={(DOMAIN, str(vehicle_id).lower())}
        )

    migrated_device = device_reg.async_get_device(
        identifiers={(DOMAIN, new_device_identifier)}
    )

    device_name = get_ovms_device_name(vehicle_id)

    if migrated_device is None and existing_device is not None:
        if _device_contains_only_config_entry_entities(
            entity_reg,
            existing_device.id,
            config_entry.entry_id,
        ):
            migrated_device = device_reg.async_update_device(
                existing_device.id,
                add_config_entry_id=config_entry.entry_id,
                new_identifiers={(DOMAIN, new_device_identifier)},
                manufacturer=OVMS_DEVICE_MANUFACTURER,
                model=OVMS_DEVICE_MODEL,
                name=device_name,
            )

    if migrated_device is None:
        migrated_device = device_reg.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={(DOMAIN, new_device_identifier)},
            manufacturer=OVMS_DEVICE_MANUFACTURER,
            model=OVMS_DEVICE_MODEL,
            name=device_name,
        )

    if existing_device and existing_device.id != migrated_device.id:
        migrated_device = _copy_device_customizations(
            device_reg,
            existing_device,
            migrated_device,
        )

    for registry_entry in registry_entries:
        new_unique_id = get_namespaced_ovms_unique_id(
            registry_entry.unique_id,
            config_entry.entry_id,
        )

        update_kwargs = {}
        if new_unique_id != registry_entry.unique_id:
            update_kwargs["new_unique_id"] = new_unique_id

        if registry_entry.device_id != migrated_device.id:
            update_kwargs["device_id"] = migrated_device.id

        if not update_kwargs:
            continue

        entity_reg.async_update_entity(registry_entry.entity_id, **update_kwargs)

        if "new_unique_id" in update_kwargs:
            _LOGGER.info(
                "V%d Migration: updated entity unique_id for %s",
                from_version,
                registry_entry.entity_id,
            )

    if existing_device and existing_device.id != migrated_device.id:
        remaining_entries = entity_registry.async_entries_for_device(
            entity_reg,
            existing_device.id,
            include_disabled_entities=True,
        )

        if not remaining_entries:
            device_reg.async_remove_device(existing_device.id)
            _LOGGER.info(
                "V%d Migration: removed legacy OVMS device %s",
                from_version,
                existing_device.id,
            )


async def async_migrate_entity_naming(
    hass: HomeAssistant, config_entry: ConfigEntry, from_version: int
) -> None:
    """Adopt Home Assistant's has_entity_name model for OVMS entities.

    Existing user-customized entity_ids are preserved. Only registry entries that
    still use the old auto-generated object_id based on the entity name alone are
    renamed to the new device-scoped form.
    """
    config = get_merged_config(config_entry)
    vehicle_id = str(config.get(CONF_VEHICLE_ID, "unknown"))
    device_name = get_ovms_device_name(vehicle_id)

    entity_reg = entity_registry.async_get(hass)
    registry_entries = entity_registry.async_entries_for_config_entry(
        entity_reg,
        config_entry.entry_id,
    )

    if not registry_entries:
        return

    current_entity_ids = set(entity_reg.entities)

    for registry_entry in registry_entries:
        if registry_entry.platform != DOMAIN:
            continue

        desired_name = _get_desired_entity_name(registry_entry, vehicle_id)
        update_kwargs = {"has_entity_name": True}

        if registry_entry.name is None and desired_name:
            if desired_name != registry_entry.original_name:
                update_kwargs["original_name"] = desired_name

            if _is_legacy_auto_entity_id(registry_entry, registry_entry.original_name):
                current_entity_ids.discard(registry_entry.entity_id)
                desired_entity_id = _generate_entity_id_from_name(
                    _get_entity_domain(registry_entry.entity_id),
                    f"{device_name} {desired_name}",
                    current_entity_ids,
                )
                current_entity_ids.add(desired_entity_id)

                if desired_entity_id != registry_entry.entity_id:
                    update_kwargs["new_entity_id"] = desired_entity_id

        if (
            update_kwargs == {"has_entity_name": True}
            and registry_entry.has_entity_name
        ):
            continue

        entity_reg.async_update_entity(registry_entry.entity_id, **update_kwargs)

        if "new_entity_id" in update_kwargs:
            _LOGGER.info(
                "V%d Migration: renamed entity_id from %s to %s",
                from_version,
                registry_entry.entity_id,
                update_kwargs["new_entity_id"],
            )


async def async_cleanup_stale_device_associations(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """Remove this config entry from OVMS devices it does not own.

    After identity migration, a config entry may still be listed in the
    config_entry_ids of devices that belong to a different OVMS entry
    (e.g. another vehicle on the same broker).  This leaves ghost devices
    visible under the integration card.

    For each OVMS device that lists *this* config entry:
    - If the device is the correct one (matches this entry's identifier) → skip.
    - Otherwise remove this config entry from that device.
    - If the device has no remaining config entries, remove it entirely.
    """
    config = get_merged_config(config_entry)
    client_id = config.get(CONF_CLIENT_ID)
    vehicle_id = config.get(CONF_VEHICLE_ID, "unknown")
    own_identifier = get_ovms_device_identifier(client_id, vehicle_id)

    device_reg = device_registry.async_get(hass)
    entity_reg = entity_registry.async_get(hass)

    # Ensure this entry's device exists with the correct identifier
    own_device = device_reg.async_get_device(identifiers={(DOMAIN, own_identifier)})
    if own_device is None:
        own_device = device_reg.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={(DOMAIN, own_identifier)},
            manufacturer=OVMS_DEVICE_MANUFACTURER,
            model=OVMS_DEVICE_MODEL,
            name=get_ovms_device_name(vehicle_id),
        )

    # Walk all devices linked to this config entry
    devices_for_entry = device_registry.async_entries_for_config_entry(
        device_reg, config_entry.entry_id
    )

    for device in devices_for_entry:
        if device.id == own_device.id:
            continue

        # Only touch OVMS devices (identified by our domain in identifiers)
        is_ovms_device = any(domain == DOMAIN for domain, _ in device.identifiers)
        if not is_ovms_device:
            continue

        # Check if this device still has entities from this config entry
        device_entities = entity_registry.async_entries_for_device(
            entity_reg, device.id, include_disabled_entities=True
        )
        has_our_entities = any(
            ent.config_entry_id == config_entry.entry_id for ent in device_entities
        )

        if has_our_entities:
            # Move orphaned entities to the correct device
            for ent in device_entities:
                if ent.config_entry_id == config_entry.entry_id:
                    entity_reg.async_update_entity(
                        ent.entity_id, device_id=own_device.id
                    )
            _LOGGER.info(
                "Device cleanup: moved entities from device %s to %s",
                device.id,
                own_device.id,
            )
            # Re-check after moving
            device_entities = entity_registry.async_entries_for_device(
                entity_reg, device.id, include_disabled_entities=True
            )

        # Detach this config entry from the foreign device
        device_reg.async_update_device(
            device.id, remove_config_entry_id=config_entry.entry_id
        )
        _LOGGER.info(
            "Device cleanup: removed config entry %s from device %s (%s)",
            config_entry.entry_id,
            device.id,
            device.name,
        )

        # If the device is now empty (no config entries, no entities), remove it
        updated_device = device_reg.async_get(device.id)
        if updated_device and not updated_device.config_entries:
            remaining = entity_registry.async_entries_for_device(
                entity_reg, device.id, include_disabled_entities=True
            )
            if not remaining:
                device_reg.async_remove_device(device.id)
                _LOGGER.info(
                    "Device cleanup: removed orphaned device %s (%s)",
                    device.id,
                    device.name,
                )
