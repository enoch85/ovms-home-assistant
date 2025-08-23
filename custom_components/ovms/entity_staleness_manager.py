"""Entity staleness manager for OVMS integration."""
import asyncio
import logging
import time
from typing import Dict, Set, Optional, Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_registry import RegistryEntryHider
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_ENTITY_STALENESS_MANAGEMENT,
    CONF_DELETE_STALE_HISTORY,
    DEFAULT_ENTITY_STALENESS_MANAGEMENT,
    DEFAULT_DELETE_STALE_HISTORY,
    LOGGER_NAME,
    SIGNAL_UPDATE_ENTITY,
)

_LOGGER = logging.getLogger(LOGGER_NAME)


class EntityStalenessManager:
    """Manager for tracking and cleaning up stale entities."""

    def __init__(self, hass: HomeAssistant, config: Dict):
        """Initialize the staleness manager."""
        self.hass = hass
        self.config = config
        self._entity_last_updates: Dict[str, float] = {}
        self._stale_entities: Set[str] = set()
        # Track base entities (without hash suffix) to handle ID changes
        self._base_entity_mapping: Dict[str, str] = {}  # base_id -> current_full_id
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

        # Convert staleness hours to seconds for internal use
        self._staleness_threshold = self._staleness_hours * 3600  # Convert hours to seconds

        _LOGGER.info(
            "Entity staleness manager initialized: enabled=%s, threshold=%d hours, delete_history=%s",
            self._enabled, self._staleness_hours, self._delete_history
        )

        if self._enabled:
            self._start_cleanup_task()

    def _get_base_entity_id(self, entity_id: str) -> str:
        """Extract base entity identity without hash suffix.
        
        Examples:
        ovms_ggk97e_metric_m_freeram_11e3ec -> ovms_ggk97e_metric_m_freeram
        sensor.ovms_ggk97e_metric_m_freeram -> sensor.ovms_ggk97e_metric_m_freeram
        """
        # Remove domain prefix if present (e.g., "sensor.")
        if "." in entity_id:
            domain, entity_part = entity_id.split(".", 1)
            base_entity = self._extract_base_from_unique_id(entity_part)
            return f"{domain}.{base_entity}"
        else:
            return self._extract_base_from_unique_id(entity_id)
    
    def _extract_base_from_unique_id(self, unique_id: str) -> str:
        """Extract base unique ID by removing hash suffix."""
        # Pattern: ovms_{vehicle}_{metric_path}_{6_char_hash}
        # We want: ovms_{vehicle}_{metric_path}
        parts = unique_id.split("_")
        if len(parts) >= 3 and len(parts[-1]) == 6:
            # Check if last part looks like a hash (6 alphanumeric chars)
            last_part = parts[-1]
            if all(c.isalnum() for c in last_part) and any(c.isdigit() for c in last_part) and any(c.isalpha() for c in last_part):
                # Remove the hash suffix
                return "_".join(parts[:-1])
        
        # If no hash pattern found, return as-is
        return unique_id

    def _start_cleanup_task(self) -> None:
        """Start the cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._async_cleanup_stale_entities())
            _LOGGER.debug("Started entity staleness cleanup task")

    def update_config(self, config: Dict) -> None:
        """Update configuration and restart cleanup task if needed."""
        old_enabled = self._enabled
        old_threshold = self._staleness_threshold
        old_delete_history = getattr(self, '_delete_history', DEFAULT_DELETE_STALE_HISTORY)

        self._staleness_hours = config.get(CONF_ENTITY_STALENESS_MANAGEMENT, DEFAULT_ENTITY_STALENESS_MANAGEMENT)
        if self._staleness_hours is None:
            self._enabled = False
            self._staleness_hours = 24  # Use 24 for calculations when needed (even though disabled)
        else:
            self._enabled = True
        self._delete_history = config.get(CONF_DELETE_STALE_HISTORY, DEFAULT_DELETE_STALE_HISTORY)
        self._staleness_threshold = self._staleness_hours * 3600

        _LOGGER.info(
            "Entity staleness configuration updated: enabled=%s, threshold=%d hours, delete_history=%s",
            self._enabled, self._staleness_hours, self._delete_history
        )

        # Restart cleanup task if settings changed
        if (old_enabled != self._enabled or old_threshold != self._staleness_threshold or
            old_delete_history != self._delete_history):
            if self._cleanup_task and not self._cleanup_task.done():
                self._cleanup_task.cancel()

            if self._enabled:
                self._start_cleanup_task()

    def track_entity_update(self, entity_id: str) -> None:
        """Track that an entity was updated."""
        if not self._enabled:
            return

        current_time = time.time()
        base_id = self._get_base_entity_id(entity_id)

        # Check if we need to transfer tracking from an old entity ID
        if base_id in self._base_entity_mapping:
            old_entity_id = self._base_entity_mapping[base_id]
            if old_entity_id != entity_id and old_entity_id in self._entity_last_updates:
                # Transfer tracking data from old ID to new ID
                self._entity_last_updates[entity_id] = current_time
                del self._entity_last_updates[old_entity_id]
                self._stale_entities.discard(old_entity_id)
                
                _LOGGER.info("Entity ID changed during update for %s: %s -> %s", 
                           base_id, old_entity_id, entity_id)
                
                # Update mapping
                self._base_entity_mapping[base_id] = entity_id
        else:
            # Update existing or create new tracking
            self._entity_last_updates[entity_id] = current_time
            self._base_entity_mapping[base_id] = entity_id

        # If entity was stale, mark it as fresh again and unhide it (if not deleted)
        if entity_id in self._stale_entities:
            self._stale_entities.remove(entity_id)
            _LOGGER.info("Entity %s is fresh again after receiving new data", entity_id)

            # Only try to unhide if we're in hide mode (not delete mode)
            if not self._delete_history:
                _LOGGER.debug("Entity %s was hidden, will restore it to UI", entity_id)
                # Schedule unhiding of the entity (async operation)
                asyncio.create_task(self._async_unhide_fresh_entities([entity_id]))

    def track_entity_creation(self, entity_id: str) -> None:
        """Track that an entity was created (but hasn't necessarily received data yet)."""
        if not self._enabled:
            return

        base_id = self._get_base_entity_id(entity_id)
        current_time = time.time()

        # Check if we're already tracking a different ID for the same base entity
        if base_id in self._base_entity_mapping:
            old_entity_id = self._base_entity_mapping[base_id]
            if old_entity_id != entity_id and old_entity_id in self._entity_last_updates:
                # Transfer tracking data from old ID to new ID
                old_timestamp = self._entity_last_updates[old_entity_id]
                self._entity_last_updates[entity_id] = old_timestamp
                
                # Clean up old tracking
                del self._entity_last_updates[old_entity_id]
                self._stale_entities.discard(old_entity_id)
                
                _LOGGER.info("Entity ID changed for %s: %s -> %s (transferred tracking data)", 
                           base_id, old_entity_id, entity_id)
            else:
                # Same entity ID, just update timestamp if not already tracked
                if entity_id not in self._entity_last_updates:
                    self._entity_last_updates[entity_id] = current_time
        else:
            # New base entity, start tracking
            self._entity_last_updates[entity_id] = current_time
            _LOGGER.debug("Started tracking newly created entity: %s (base: %s, total tracked: %d)", 
                         entity_id, base_id, len(self._entity_last_updates))

        # Update the mapping
        self._base_entity_mapping[base_id] = entity_id

    def is_entity_stale(self, entity_id: str) -> bool:
        """Check if an entity is considered stale."""
        if not self._enabled:
            return False

        if entity_id not in self._entity_last_updates:
            return False  # No update time recorded, assume fresh

        age = time.time() - self._entity_last_updates[entity_id]
        return age > self._staleness_threshold

    def get_entity_age_hours(self, entity_id: str) -> Optional[float]:
        """Get the age of an entity in hours."""
        if entity_id not in self._entity_last_updates:
            return None

        age_seconds = time.time() - self._entity_last_updates[entity_id]
        return age_seconds / 3600

    def get_stale_entities(self) -> Set[str]:
        """Get a copy of the current stale entities set."""
        return self._stale_entities.copy()

    def get_entity_stats(self) -> Dict[str, int]:
        """Get statistics about tracked entities."""
        current_time = time.time()
        stale_count = 0
        fresh_count = 0

        for entity_id, last_update in self._entity_last_updates.items():
            age = current_time - last_update
            if age > self._staleness_threshold:
                stale_count += 1
            else:
                fresh_count += 1

        return {
            "total_tracked": len(self._entity_last_updates),
            "fresh_entities": fresh_count,
            "stale_entities": stale_count,
            "staleness_threshold_hours": self._staleness_hours,
            "enabled": self._enabled,
        }

    async def _async_cleanup_stale_entities(self) -> None:
        """Periodically clean up stale entities."""
        _LOGGER.debug("Entity staleness cleanup task started")

        while not self._shutting_down:
            try:
                # Run cleanup every hour
                await asyncio.sleep(3600)  # 1 hour

                if not self._enabled:
                    continue

                current_time = time.time()
                newly_stale_entities = []

                _LOGGER.debug("Staleness cleanup running, checking %d tracked entities", len(self._entity_last_updates))

                for entity_id, last_update_time in self._entity_last_updates.items():
                    age = current_time - last_update_time

                    if age > self._staleness_threshold and entity_id not in self._stale_entities:
                        # Entity just became stale
                        self._stale_entities.add(entity_id)
                        newly_stale_entities.append(entity_id)

                        _LOGGER.debug(
                            "Entity %s became stale after %.1f hours of inactivity (threshold: %.1f hours)",
                            entity_id, age / 3600, self._staleness_threshold / 3600
                        )

                if newly_stale_entities:
                    if self._delete_history:
                        _LOGGER.info(
                            "Found %d stale entities (older than %.1f hours), removing them completely (including history)",
                            len(newly_stale_entities), self._staleness_threshold / 3600
                        )
                        # Delete entities completely including history
                        await self._async_remove_stale_entities(newly_stale_entities)
                    else:
                        _LOGGER.info(
                            "Found %d stale entities (older than %.1f hours), hiding them to reduce UI clutter while preserving history",
                            len(newly_stale_entities), self._staleness_threshold / 3600
                        )
                        # Hide stale entities from UI while preserving their history
                        await self._async_hide_stale_entities(newly_stale_entities)

            except asyncio.CancelledError:
                _LOGGER.debug("Entity staleness cleanup task cancelled")
                break
            except Exception as ex:  # pylint: disable=broad-except
                _LOGGER.exception("Error in entity staleness cleanup: %s", ex)
                # Wait a bit before retrying to avoid tight loop
                await asyncio.sleep(300)  # 5 minutes

        _LOGGER.debug("Entity staleness cleanup task stopped")

    async def _async_hide_stale_entities(self, stale_entity_ids: list) -> None:
        """Hide stale entities from UI while preserving their history."""
        try:
            # Get Home Assistant's entity registry
            entity_registry = er.async_get(self.hass)

            hidden_count = 0
            for entity_id in stale_entity_ids:
                try:
                    # Check if entity exists in HA's registry
                    entity_entry = entity_registry.async_get(entity_id)
                    if entity_entry and not entity_entry.hidden_by:
                        # Hide the entity from UI while preserving history
                        entity_registry.async_update_entity(
                            entity_id,
                            hidden_by=RegistryEntryHider.USER
                        )
                        hidden_count += 1
                        _LOGGER.info("Hidden stale entity from UI: %s (history preserved)", entity_id)

                        # Keep entity in our tracking since it's just hidden, not removed
                    elif entity_entry and entity_entry.hidden_by:
                        _LOGGER.debug("Entity %s already hidden", entity_id)
                    else:
                        _LOGGER.info("Entity %s not found in registry, cleaning up tracking", entity_id)
                        # Clean up our tracking if entity doesn't exist
                        self._entity_last_updates.pop(entity_id, None)
                        self._stale_entities.discard(entity_id)

                except Exception as ex:
                    _LOGGER.warning("Failed to hide stale entity %s: %s", entity_id, ex)

            if hidden_count > 0:
                _LOGGER.info(
                    "Successfully hidden %d stale entities from UI (history preserved). Total tracking %d entities.",
                    hidden_count, len(self._entity_last_updates)
                )

        except Exception as ex:
            _LOGGER.exception("Error hiding stale entities: %s", ex)

    async def _async_remove_stale_entities(self, stale_entity_ids: list) -> None:
        """Completely remove stale entities from Home Assistant including history."""
        try:
            # Get Home Assistant's entity registry
            entity_registry = er.async_get(self.hass)

            removed_count = 0
            for entity_id in stale_entity_ids:
                try:
                    # Check if entity exists in HA's registry
                    entity_entry = entity_registry.async_get(entity_id)
                    if entity_entry:
                        # Remove the entity completely from Home Assistant
                        entity_registry.async_remove(entity_id)
                        removed_count += 1
                        _LOGGER.info("Permanently removed stale entity: %s (including all history)", entity_id)

                        # Remove from our tracking as well
                        self._entity_last_updates.pop(entity_id, None)
                        self._stale_entities.discard(entity_id)
                    else:
                        _LOGGER.info("Entity %s not found in registry, cleaning up tracking", entity_id)
                        # Clean up our tracking even if entity doesn't exist
                        self._entity_last_updates.pop(entity_id, None)
                        self._stale_entities.discard(entity_id)

                except Exception as ex:
                    _LOGGER.warning("Failed to remove stale entity %s: %s", entity_id, ex)

            if removed_count > 0:
                _LOGGER.info(
                    "Successfully removed %d stale entities completely from Home Assistant (including history). Total tracking %d entities.",
                    removed_count, len(self._entity_last_updates)
                )

        except Exception as ex:
            _LOGGER.exception("Error removing stale entities: %s", ex)

    async def _async_unhide_fresh_entities(self, fresh_entity_ids: list) -> None:
        """Unhide entities that have become fresh again."""
        try:
            # Get Home Assistant's entity registry
            entity_registry = er.async_get(self.hass)

            unhidden_count = 0
            for entity_id in fresh_entity_ids:
                try:
                    # Check if entity exists and is hidden
                    entity_entry = entity_registry.async_get(entity_id)
                    if entity_entry and entity_entry.hidden_by == RegistryEntryHider.USER:
                        # Unhide the entity since it's fresh again
                        entity_registry.async_update_entity(
                            entity_id,
                            hidden_by=None
                        )
                        unhidden_count += 1
                        _LOGGER.debug("Unhidden fresh entity: %s (restored to UI)", entity_id)

                except Exception as ex:
                    _LOGGER.warning("Failed to unhide fresh entity %s: %s", entity_id, ex)

            if unhidden_count > 0:
                _LOGGER.debug(
                    "Successfully restored %d fresh entities to UI. Total tracking %d entities.",
                    unhidden_count, len(self._entity_last_updates)
                )

        except Exception as ex:
            _LOGGER.exception("Error unhiding fresh entities: %s", ex)

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

    def remove_entity(self, entity_id: str) -> None:
        """Remove an entity from tracking (e.g., when entity is deleted)."""
        self._entity_last_updates.pop(entity_id, None)
        self._stale_entities.discard(entity_id)
        
        # Also clean up base mapping if this was the current entity for its base
        base_id = self._get_base_entity_id(entity_id)
        if self._base_entity_mapping.get(base_id) == entity_id:
            del self._base_entity_mapping[base_id]
            
        _LOGGER.debug("Removed entity %s from staleness tracking", entity_id)
