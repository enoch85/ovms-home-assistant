"""Entity staleness manager for OVMS integration."""
import asyncio
import logging
import time
from typing import Dict, Set, Optional, Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_ENTITY_STALENESS_HOURS,
    CONF_ENABLE_STALENESS_CLEANUP,
    DEFAULT_ENTITY_STALENESS_HOURS,
    DEFAULT_ENABLE_STALENESS_CLEANUP,
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
        self._cleanup_task: Optional[asyncio.Task] = None
        self._shutting_down = False
        
        # Get configuration
        self._enabled = config.get(CONF_ENABLE_STALENESS_CLEANUP, DEFAULT_ENABLE_STALENESS_CLEANUP)
        self._staleness_hours = config.get(CONF_ENTITY_STALENESS_HOURS, DEFAULT_ENTITY_STALENESS_HOURS)
        self._staleness_threshold = self._staleness_hours * 3600  # Convert to seconds
        
        _LOGGER.info(
            "Entity staleness manager initialized: enabled=%s, threshold=%d hours",
            self._enabled, self._staleness_hours
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
        old_threshold = self._staleness_threshold
        
        self._enabled = config.get(CONF_ENABLE_STALENESS_CLEANUP, DEFAULT_ENABLE_STALENESS_CLEANUP)
        self._staleness_hours = config.get(CONF_ENTITY_STALENESS_HOURS, DEFAULT_ENTITY_STALENESS_HOURS)
        self._staleness_threshold = self._staleness_hours * 3600
        
        _LOGGER.info(
            "Entity staleness configuration updated: enabled=%s, threshold=%d hours",
            self._enabled, self._staleness_hours
        )
        
        # Restart cleanup task if settings changed
        if old_enabled != self._enabled or old_threshold != self._staleness_threshold:
            if self._cleanup_task and not self._cleanup_task.done():
                self._cleanup_task.cancel()
            
            if self._enabled:
                self._start_cleanup_task()

    def track_entity_update(self, entity_id: str) -> None:
        """Track that an entity was updated."""
        if not self._enabled:
            return
            
        current_time = time.time()
        self._entity_last_updates[entity_id] = current_time
        
        # If entity was stale, mark it as fresh again
        if entity_id in self._stale_entities:
            self._stale_entities.remove(entity_id)
            _LOGGER.debug("Entity %s is fresh again", entity_id)

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
                await asyncio.sleep(3600)
                
                if not self._enabled:
                    continue
                    
                current_time = time.time()
                newly_stale_entities = []
                
                for entity_id, last_update_time in self._entity_last_updates.items():
                    age = current_time - last_update_time
                    
                    if age > self._staleness_threshold and entity_id not in self._stale_entities:
                        # Entity just became stale
                        self._stale_entities.add(entity_id)
                        newly_stale_entities.append(entity_id)
                        
                        _LOGGER.debug(
                            "Entity %s became stale (age: %.1f hours)", 
                            entity_id, age / 3600
                        )
                
                if newly_stale_entities:
                    _LOGGER.info(
                        "Marked %d entities as stale (older than %d hours)",
                        len(newly_stale_entities), self._staleness_hours
                    )
                    
                    # Send staleness update signal for each newly stale entity
                    for entity_id in newly_stale_entities:
                        async_dispatcher_send(
                            self.hass,
                            f"{SIGNAL_UPDATE_ENTITY}_{entity_id}_staleness",
                            True  # True indicates the entity is now stale
                        )
                
            except asyncio.CancelledError:
                _LOGGER.debug("Entity staleness cleanup task cancelled")
                break
            except Exception as ex:  # pylint: disable=broad-except
                _LOGGER.exception("Error in entity staleness cleanup: %s", ex)
                # Wait a bit before retrying to avoid tight loop
                await asyncio.sleep(300)  # 5 minutes
                
        _LOGGER.debug("Entity staleness cleanup task stopped")

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
        _LOGGER.debug("Removed entity %s from staleness tracking", entity_id)
