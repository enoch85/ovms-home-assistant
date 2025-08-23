"""Entity staleness manager for OVMS integration."""
import asyncio
import logging
from typing import Dict, Optional

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_registry import RegistryEntryHider
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from .const import (
    CONF_ENTITY_STALENESS_MANAGEMENT,
    CONF_DELETE_STALE_HISTORY,
    DEFAULT_ENTITY_STALENESS_MANAGEMENT,
    DEFAULT_DELETE_STALE_HISTORY,
    LOGGER_NAME,
)

_LOGGER = logging.getLogger(LOGGER_NAME)


class EntityStalenessManager:
    """Manager for cleaning up stale entities based on Home Assistant's built-in availability."""

    def __init__(self, hass: HomeAssistant, config: Dict):
        """Initialize the staleness manager."""
        self.hass = hass
        self.config = config
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutting_down = False

        # Get configuration - None means disabled, any number means enabled
        self._staleness_hours = config.get(CONF_ENTITY_STALENESS_MANAGEMENT, DEFAULT_ENTITY_STALENESS_MANAGEMENT)
        if self._staleness_hours is None:
            self._enabled = False
            self._staleness_hours = 24  # Use 24 for calculations when needed (even though disabled)
        else:
            self._enabled = True
        self._delete_history = config.get(CONF_DELETE_STALE_HISTORY, DEFAULT_DELETE_STALE_HISTORY)

        _LOGGER.info(
            "Entity staleness manager initialized: enabled=%s, threshold=%d hours, delete_history=%s",
            self._enabled, self._staleness_hours, self._delete_history
        )

        if self._enabled:
            self._start_cleanup_task()

    def _start_cleanup_task(self) -> None:
        """Start the cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._async_cleanup_stale_entities())
            _LOGGER.debug("Started entity staleness cleanup task")

    def update_config(self, config: Dict) -> None:
        """Update configuration and restart cleanup task if needed."""
        old_enabled = self._enabled
        old_staleness_hours = self._staleness_hours
        old_delete_history = self._delete_history

        self._staleness_hours = config.get(CONF_ENTITY_STALENESS_MANAGEMENT, DEFAULT_ENTITY_STALENESS_MANAGEMENT)
        if self._staleness_hours is None:
            self._enabled = False
            self._staleness_hours = 24  # Use 24 for calculations when needed (even though disabled)
        else:
            self._enabled = True
        self._delete_history = config.get(CONF_DELETE_STALE_HISTORY, DEFAULT_DELETE_STALE_HISTORY)

        _LOGGER.info(
            "Entity staleness configuration updated: enabled=%s, threshold=%d hours, delete_history=%s",
            self._enabled, self._staleness_hours, self._delete_history
        )

        # Restart cleanup task if settings changed
        if (old_enabled != self._enabled or old_staleness_hours != self._staleness_hours or
            old_delete_history != self._delete_history):
            if self._cleanup_task and not self._cleanup_task.done():
                self._cleanup_task.cancel()

            if self._enabled:
                self._start_cleanup_task()

    def get_entity_stats(self) -> Dict[str, int]:
        """Get statistics about OVMS entities."""
        entity_registry = er.async_get(self.hass)
        
        total_ovms = 0
        available_ovms = 0
        unavailable_ovms = 0
        
        # Count OVMS entities and their states
        for entity_id in entity_registry.entities:
            if entity_id.startswith(("sensor.ovms_", "binary_sensor.ovms_", "switch.ovms_", "device_tracker.ovms_")):
                total_ovms += 1
                state = self.hass.states.get(entity_id)
                if state and state.state in [STATE_UNAVAILABLE, STATE_UNKNOWN]:
                    unavailable_ovms += 1
                else:
                    available_ovms += 1

        return {
            "total_ovms_entities": total_ovms,
            "available_entities": available_ovms,
            "unavailable_entities": unavailable_ovms,
            "staleness_threshold_hours": self._staleness_hours,
            "enabled": self._enabled,
        }

    async def _async_cleanup_stale_entities(self) -> None:
        """Periodically clean up entities that Home Assistant marks as unavailable."""
        _LOGGER.debug("Entity staleness cleanup task started")

        while not self._shutting_down:
            try:
                # Run cleanup every hour
                await asyncio.sleep(3600)  # 1 hour

                if not self._enabled:
                    continue

                await self._cleanup_unavailable_entities()

            except asyncio.CancelledError:
                _LOGGER.debug("Entity staleness cleanup task cancelled")
                break
            except Exception as ex:  # pylint: disable=broad-except
                _LOGGER.exception("Error in entity staleness cleanup: %s", ex)
                # Wait a bit before retrying to avoid tight loop
                await asyncio.sleep(300)  # 5 minutes

        _LOGGER.debug("Entity staleness cleanup task stopped")

    async def _cleanup_unavailable_entities(self) -> None:
        """Clean up entities that Home Assistant has marked as unavailable."""
        try:
            entity_registry = er.async_get(self.hass)
            unavailable_entities = []

            # Find OVMS entities that are unavailable
            for entity_id in entity_registry.entities:
                # Only process OVMS entities
                if not entity_id.startswith(("sensor.ovms_", "binary_sensor.ovms_", "switch.ovms_", "device_tracker.ovms_")):
                    continue

                # Check if entity is unavailable in Home Assistant's state machine
                state = self.hass.states.get(entity_id)
                if state and state.state in [STATE_UNAVAILABLE, STATE_UNKNOWN]:
                    # Check how long it's been unavailable
                    if hasattr(state, 'last_updated') and state.last_updated:
                        hours_unavailable = (self.hass.loop.time() - state.last_updated.timestamp()) / 3600
                        
                        if hours_unavailable > self._staleness_hours:
                            unavailable_entities.append((entity_id, hours_unavailable))

            if unavailable_entities:
                entity_ids = [entity_id for entity_id, _ in unavailable_entities]
                
                if self._delete_history:
                    _LOGGER.info(
                        "Found %d unavailable OVMS entities (unavailable for >%d hours), removing them completely",
                        len(unavailable_entities), self._staleness_hours
                    )
                    await self._async_remove_entities(entity_ids)
                else:
                    _LOGGER.info(
                        "Found %d unavailable OVMS entities (unavailable for >%d hours), hiding them from UI",
                        len(unavailable_entities), self._staleness_hours
                    )
                    await self._async_hide_entities(entity_ids)

        except Exception as ex:
            _LOGGER.exception("Error cleaning up unavailable entities: %s", ex)

    async def _async_hide_entities(self, entity_ids: list) -> None:
        """Hide entities from UI while preserving their history."""
        try:
            entity_registry = er.async_get(self.hass)
            hidden_count = 0
            
            for entity_id in entity_ids:
                try:
                    entity_entry = entity_registry.async_get(entity_id)
                    if entity_entry and not entity_entry.hidden_by:
                        entity_registry.async_update_entity(
                            entity_id,
                            hidden_by=RegistryEntryHider.USER
                        )
                        hidden_count += 1
                        _LOGGER.debug("Hidden unavailable entity from UI: %s", entity_id)
                    elif entity_entry and entity_entry.hidden_by:
                        _LOGGER.debug("Entity %s already hidden", entity_id)
                    else:
                        _LOGGER.debug("Entity %s not found in registry", entity_id)

                except Exception as ex:
                    _LOGGER.warning("Failed to hide entity %s: %s", entity_id, ex)

            if hidden_count > 0:
                _LOGGER.info("Successfully hidden %d unavailable entities from UI", hidden_count)

        except Exception as ex:
            _LOGGER.exception("Error hiding entities: %s", ex)

    async def _async_remove_entities(self, entity_ids: list) -> None:
        """Completely remove entities from Home Assistant including history."""
        try:
            entity_registry = er.async_get(self.hass)
            removed_count = 0
            
            for entity_id in entity_ids:
                try:
                    entity_entry = entity_registry.async_get(entity_id)
                    if entity_entry:
                        entity_registry.async_remove(entity_id)
                        removed_count += 1
                        _LOGGER.debug("Permanently removed unavailable entity: %s", entity_id)
                    else:
                        _LOGGER.debug("Entity %s not found in registry", entity_id)

                except Exception as ex:
                    _LOGGER.warning("Failed to remove entity %s: %s", entity_id, ex)

            if removed_count > 0:
                _LOGGER.info("Successfully removed %d unavailable entities completely", removed_count)

        except Exception as ex:
            _LOGGER.exception("Error removing entities: %s", ex)

    async def async_shutdown(self) -> None:
        """Shutdown the staleness manager."""
        _LOGGER.debug("Shutting down entity staleness manager")
        self._shutting_down = True

        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        _LOGGER.debug("Entity staleness manager shut down complete")
