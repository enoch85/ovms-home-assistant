"""Config-entry migration helpers for the OVMS integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry

from .const import DOMAIN, LOGGER_NAME

_LOGGER = logging.getLogger(LOGGER_NAME)

_LEGACY_LOCK_METRIC_MARKER = "_v_e_locked_"
_SWITCH_SUFFIX = "_switch"
_LOCK_SUFFIX = "_lock"


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
