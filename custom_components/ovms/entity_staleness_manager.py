"""Entity staleness manager for OVMS integration."""
import asyncio
import logging
from typing import Dict, Optional, List, Any
from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_registry import RegistryEntryHider
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later
from homeassistant.const import EntityCategory
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ENTITY_STALENESS_MANAGEMENT,
    CONF_DELETE_STALE_HISTORY,
    CONF_VEHICLE_ID,
    DEFAULT_ENTITY_STALENESS_MANAGEMENT,
    DEFAULT_DELETE_STALE_HISTORY,
    LOGGER_NAME,
    SIGNAL_ADD_ENTITIES,
    DOMAIN,
    STALENESS_INITIAL_CACHE_DELAY,
    STALENESS_DIAGNOSTIC_SENSOR_DELAY,
    STALENESS_CLEANUP_START_DELAY,
    STALENESS_CLEANUP_INTERVAL,
    STALENESS_FIRST_RUN_EXTRA_WAIT,
)

_LOGGER = logging.getLogger(LOGGER_NAME)


def _is_ovms_entity(entity_id: str) -> bool:
    """Return True if the entity belongs to the OVMS integration."""
    return entity_id.startswith(
        ("sensor.ovms_", "binary_sensor.ovms_", "switch.ovms_", "device_tracker.ovms_")
    )


class OVMSStalenessStatusSensor(SensorEntity, RestoreEntity):
    """Diagnostic sensor showing count of entities scheduled for removal."""

    _attr_name = "OVMS Staleness Status"
    _attr_unique_id = "ovms_staleness_status"
    _attr_icon = "mdi:clock-alert-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_unit_of_measurement = "entities"
    _attr_entity_registry_enabled_default = False  # Hidden by default in UI

    def __init__(self, staleness_manager: "EntityStalenessManager", device_info: Dict[str, Any]) -> None:
        """Initialize the sensor."""
        self._manager = staleness_manager
        self._attr_device_info = device_info
        self._restored_data: Dict[str, Any] = {}

    @property
    def native_value(self) -> int:
        """Return the number of entities scheduled for removal."""
        # Use manager's cache first, fall back to restored data if cache not ready
        cache_count = self._manager._cache.get("count")
        if cache_count is not None:
            return cache_count
        return self._restored_data.get("count", 0)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return cached staleness information (non-blocking)."""
        # Use manager's cache first, fall back to restored data if cache not ready
        cache = self._manager._cache
        if cache.get("count") is not None:
            return cache.copy()
        return self._restored_data.copy()

    async def async_added_to_hass(self) -> None:
        """Restore previous state when added to Home Assistant."""
        await super().async_added_to_hass()
        
        # Restore the last known state
        last_state = await self.async_get_last_state()
        if last_state is not None:
            # Restore numeric state
            try:
                restored_count = int(last_state.state) if last_state.state.isdigit() else 0
                self._restored_data["count"] = restored_count
            except (ValueError, AttributeError):
                self._restored_data["count"] = 0
            
            # Restore attributes if available
            if last_state.attributes:
                self._restored_data.update(last_state.attributes)
                
        _LOGGER.debug("Restored staleness sensor state: count=%d", self._restored_data.get("count", 0))


class EntityStalenessManager:
    """Manager for cleaning up stale entities based on Home Assistant's built-in availability."""

    def __init__(self, hass: HomeAssistant, config: Dict[str, Any]) -> None:
        """Initialize the staleness manager."""
        self.hass = hass
        self.config = config
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutting_down = False
        
        # Simple cache - gets populated immediately when enabled
        self._cache = {
            "count": 0,
            "pending_entities": "Waiting...",
            "staleness_enabled": False,
            "staleness_threshold_hours": 0,
            "action": "hide",
            "last_check": "Not yet checked",
            "errors": 0,  # Error counter for debugging
            "last_error": None,  # Last error message
        }

        # Get configuration
        self._staleness_hours = config.get(CONF_ENTITY_STALENESS_MANAGEMENT, DEFAULT_ENTITY_STALENESS_MANAGEMENT)
        self._enabled = self._staleness_hours is not None
        self._delete_history = config.get(CONF_DELETE_STALE_HISTORY, DEFAULT_DELETE_STALE_HISTORY)

        # Update cache with actual config
        self._cache.update({
            "staleness_enabled": self._enabled,
            "staleness_threshold_hours": self._staleness_hours or "disabled",
            "action": "delete" if self._delete_history else "hide",
        })

        _LOGGER.info("Staleness manager: enabled=%s", self._enabled)
        if self._enabled:
            _LOGGER.info("Staleness threshold: %dh", self._staleness_hours)

        # Schedule background tasks (non-blocking) - only if enabled
        if self._enabled:
            async_call_later(self.hass, STALENESS_CLEANUP_START_DELAY, lambda _: self._schedule_cleanup_task())
            async_call_later(self.hass, STALENESS_DIAGNOSTIC_SENSOR_DELAY, lambda _: self._schedule_diagnostic_sensor())
            # Do an immediate cache update (non-blocking) to show current status right away
            async_call_later(self.hass, STALENESS_INITIAL_CACHE_DELAY, lambda _: self._update_cache_immediately())

    def _schedule_cleanup_task(self) -> None:
        """Schedule the cleanup task to start (called by async_call_later)."""
        if not self._shutting_down and self._enabled:
            # Use call_soon_threadsafe to get back to the event loop
            self.hass.loop.call_soon_threadsafe(self._start_cleanup_task)

    def _schedule_diagnostic_sensor(self) -> None:
        """Schedule diagnostic sensor creation (called by async_call_later)."""
        if not self._shutting_down:
            # Use call_soon_threadsafe to get back to the event loop
            self.hass.loop.call_soon_threadsafe(
                lambda: self.hass.async_create_task(self._async_create_diagnostic_sensor())
            )

    def _update_cache_immediately(self) -> None:
        """Update cache immediately on startup to show current status (called by async_call_later)."""
        if not self._shutting_down and self._enabled:
            # Safe to call from thread since it's synchronous
            self.get_staleness_info()

    async def _async_create_diagnostic_sensor(self) -> None:
        """Create a simple diagnostic sensor asynchronously."""
        # No additional delay needed here since call_later already handled the timing
        
        # Create device info for the diagnostic sensor
        vehicle_id = self.config.get(CONF_VEHICLE_ID, "unknown")
        device_info = {
            "identifiers": {(DOMAIN, vehicle_id)},
            "name": f"OVMS - {vehicle_id}",
            "manufacturer": "Open Vehicles",
            "model": "OVMS v3",
        }

        sensor = OVMSStalenessStatusSensor(self, device_info)

        sensor_data = {
            "entity_type": "sensor",
            "diagnostic_sensor": sensor
        }

        # Send to sensor platform
        async_dispatcher_send(self.hass, SIGNAL_ADD_ENTITIES, sensor_data)
        _LOGGER.debug("Diagnostic sensor creation signal sent")

    def _start_cleanup_task(self) -> None:
        """Start the cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = self.hass.async_create_task(self._async_cleanup_stale_entities())
            _LOGGER.debug("Started entity staleness cleanup task")

    def update_config(self, config: Dict[str, Any]) -> None:
        """Update configuration and restart cleanup task if needed."""
        old_enabled = self._enabled
        
        self._staleness_hours = config.get(CONF_ENTITY_STALENESS_MANAGEMENT, DEFAULT_ENTITY_STALENESS_MANAGEMENT)
        self._enabled = self._staleness_hours is not None
        self._delete_history = config.get(CONF_DELETE_STALE_HISTORY, DEFAULT_DELETE_STALE_HISTORY)

        # Update cache with new config
        self._cache.update({
            "staleness_enabled": self._enabled,
            "action": "delete" if self._delete_history else "hide",
            "pending_entities": "Config updated - waiting...",
        })
        
        if self._enabled:
            self._cache["staleness_threshold_hours"] = self._staleness_hours
            _LOGGER.info("Staleness config updated: enabled=True, threshold=%dh", self._staleness_hours)
        else:
            self._cache["staleness_threshold_hours"] = "disabled"
            _LOGGER.info("Staleness config updated: enabled=False")

        # Restart cleanup task if needed
        if old_enabled != self._enabled:
            if self._cleanup_task and not self._cleanup_task.done():
                self._cleanup_task.cancel()
            if self._enabled:
                self._start_cleanup_task()

    def get_staleness_info(self) -> Dict[str, Any]:
        """Update cache with current staleness information (called from background task)."""
        # Don't process if staleness management is disabled
        if not self._enabled:
            self._cache.update({
                "count": 0,
                "pending_entities": "Staleness management is disabled",
                "last_check": dt_util.utcnow().isoformat(),
            })
            return self._cache
            
        try:
            entity_registry = er.async_get(self.hass)
            current_time = dt_util.utcnow()
            stale_entities = []
            
            # Iterate through entity registry entries directly for better performance
            for entity_id, entity_entry in entity_registry.entities.items():
                if not _is_ovms_entity(entity_id):
                    continue

                state = self.hass.states.get(entity_id)
                if state and state.state in ["unavailable", "unknown"] and hasattr(state, 'last_updated') and state.last_updated:
                    hours_stale = (current_time - state.last_updated).total_seconds() / 3600
                    
                    # Use friendly name from entity registry entry (already have it from the loop)
                    friendly_name = entity_entry.name if entity_entry.name else entity_id
                    
                    # Cap at 40 entities for clean display
                    if len(stale_entities) < 40:
                        if hours_stale > self._staleness_hours:
                            stale_entities.append(f"{friendly_name} (eligible for removal)")
                        else:
                            remaining = round(self._staleness_hours - hours_stale, 1)
                            stale_entities.append(f"{friendly_name} ({remaining}h)")

            # Update cache
            self._cache.update({
                "count": len(stale_entities),
                "pending_entities": "\n".join(stale_entities) if stale_entities else "No stale entities",
                "last_check": current_time.isoformat(),
            })
            
            if len(stale_entities) >= 40:
                self._cache["entities_note"] = f"Showing first 40 entities"

            return self._cache

        except Exception as ex:
            _LOGGER.exception("Error getting staleness info: %s", ex)
            self._cache.update({
                "count": 0,
                "pending_entities": f"Error: {str(ex)}",
                "last_check": dt_util.utcnow().isoformat(),
                "errors": self._cache.get("errors", 0) + 1,
                "last_error": str(ex),
            })
            return self._cache

    async def _async_cleanup_stale_entities(self) -> None:
        """Periodically clean up entities that Home Assistant marks as unavailable."""
        _LOGGER.debug("Entity staleness cleanup task started")

        # Since call_later already handled the initial delay, we can start with a cleanup
        # Give a bit more time for HA to be fully ready, but don't block initialization
        try:
            if self._enabled:
                _LOGGER.debug("Waiting additional %d seconds for HA to fully stabilize before first cleanup", STALENESS_FIRST_RUN_EXTRA_WAIT)
                await asyncio.sleep(STALENESS_FIRST_RUN_EXTRA_WAIT)
                if not self._shutting_down:
                    _LOGGER.debug("Running initial staleness cleanup")
                    await self._cleanup_unavailable_entities()
                    # Update cache after initial cleanup
                    self.get_staleness_info()
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.exception("Error in initial staleness cleanup: %s", ex)

        while not self._shutting_down:
            try:
                # Wait between cleanups
                await asyncio.sleep(STALENESS_CLEANUP_INTERVAL)

                if not self._enabled:
                    continue

                await self._cleanup_unavailable_entities()
                # Update cache after cleanup
                self.get_staleness_info()

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
            current_time = dt_util.utcnow()

            # Find OVMS entities that are unavailable
            for entity_id, entity_entry in entity_registry.entities.items():
                # Only process OVMS entities
                if not _is_ovms_entity(entity_id):
                    continue

                # Check if entity is unavailable in Home Assistant's state machine
                state = self.hass.states.get(entity_id)
                if state and state.state in ["unavailable", "unknown"]:
                    # Use Home Assistant's built-in state.last_updated to determine staleness
                    if hasattr(state, 'last_updated') and state.last_updated:
                        hours_unavailable = (current_time - state.last_updated).total_seconds() / 3600

                        if hours_unavailable > self._staleness_hours:
                            unavailable_entities.append((entity_id, hours_unavailable, state.last_updated))

            if unavailable_entities:
                entity_ids = [entity_id for entity_id, _, _ in unavailable_entities]

                if self._delete_history:
                    _LOGGER.info(
                        "Found %d unavailable OVMS entities (unavailable for >%d hours), removing them completely",
                        len(unavailable_entities), self._staleness_hours
                    )
                    # Log details for debugging
                    for entity_id, hours, last_updated in unavailable_entities:
                        _LOGGER.debug("Removing %s: last updated %s (%.1f hours ago)",
                                    entity_id, last_updated.isoformat(), hours)
                    await self._async_remove_entities(entity_ids)
                else:
                    _LOGGER.info(
                        "Found %d unavailable OVMS entities (unavailable for >%d hours), hiding them from UI",
                        len(unavailable_entities), self._staleness_hours
                    )
                    # Log details for debugging
                    for entity_id, hours, last_updated in unavailable_entities:
                        _LOGGER.debug("Hiding %s: last updated %s (%.1f hours ago)",
                                    entity_id, last_updated.isoformat(), hours)
                    await self._async_hide_entities(entity_ids)

        except Exception as ex:
            _LOGGER.exception("Error cleaning up unavailable entities: %s", ex)

    async def _async_hide_entities(self, entity_ids: List[str]) -> None:
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

    async def _async_remove_entities(self, entity_ids: List[str]) -> None:
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
