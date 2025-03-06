"""Base entity for OVMS integration."""
import logging
import json
from typing import Any, Dict, Optional, Callable, Union

from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, LOGGER_NAME, SIGNAL_UPDATE_ENTITY

_LOGGER = logging.getLogger(LOGGER_NAME)

class OVMSBaseEntity(Entity, RestoreEntity):
    """Base entity class for OVMS entities."""
    
    def __init__(
        self,
        unique_id: str,
        name: str,
        topic: str,
        initial_state: Any,
        device_info: DeviceInfo,
        attributes: Dict[str, Any],
        friendly_name: Optional[str] = None,
    ) -> None:
        """Initialize the entity.
        
        Args:
            unique_id: Unique identifier for this entity
            name: Entity name (will be transformed to entity_id)
            topic: MQTT topic this entity is based on
            initial_state: Initial state from MQTT
            device_info: Device info for this entity
            attributes: Additional attributes for this entity
            friendly_name: User-friendly name (optional)
        """
        self._attr_unique_id = unique_id
        self._internal_name = name
        self._attr_name = friendly_name or name.replace("_", " ").title()
        self._topic = topic
        self._attr_device_info = device_info
        self._attr_extra_state_attributes = {
            **attributes,
            "topic": topic,
            "last_updated": dt_util.utcnow().isoformat(),
        }
        
        # Parse initial state
        self._process_initial_state(initial_state)
        
    def _process_initial_state(self, initial_state: Any) -> None:
        """Process the initial state - to be implemented by child classes."""
        pass
        
    async def async_added_to_hass(self) -> None:
        """Handle entity addition to Home Assistant.
        
        Sets up state restoration from disk and subscribes to update events.
        """
        await super().async_added_to_hass()
        
        # Restore previous state if available
        await self._restore_state()
        
        # Connect to dispatcher for state updates
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_UPDATE_ENTITY}_{self.unique_id}",
                self._handle_update,
            )
        )
    
    async def _restore_state(self) -> None:
        """Restore previous entity state from Home Assistant storage."""
        if (state := await self.async_get_last_state()) is not None:
            await self._handle_restore_state(state)
    
    async def _handle_restore_state(self, state) -> None:
        """Process the restored state - to be implemented by child classes."""
        pass
    
    def _handle_update(self, payload: str) -> None:
        """Handle state updates - to be implemented by child classes."""
        # Update timestamp
        now = dt_util.utcnow()
        self._attr_extra_state_attributes["last_updated"] = now.isoformat()
        
        # Process JSON payload if available
        self._process_json_payload(payload)
        
    def _process_json_payload(self, payload: str) -> None:
        """Process JSON payload to extract additional attributes."""
        try:
            json_data = json.loads(payload)
            if isinstance(json_data, dict):
                # Add useful attributes from the data
                for key, value in json_data.items():
                    if key not in ["value", "state", "data"] and key not in self._attr_extra_state_attributes:
                        self._attr_extra_state_attributes[key] = value
                        
                # If there's a timestamp in the JSON, use it
                if "timestamp" in json_data:
                    self._attr_extra_state_attributes["device_timestamp"] = json_data["timestamp"]
                    
        except (ValueError, json.JSONDecodeError):
            # Not JSON, that's fine
            pass

    def _is_special_state_value(self, value: Any) -> bool:
        """Check if a value is a special state value that should be converted to None."""
        if value is None:
            return True
        if isinstance(value, str) and value.lower() in ["unavailable", "unknown", "none", "", "null", "nan"]:
            return True
        return False
