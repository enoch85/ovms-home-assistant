"""Support for OVMS binary sensors."""
import logging
from typing import Any, Dict, Optional

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, LOGGER_NAME
from .mqtt import SIGNAL_ADD_ENTITIES, SIGNAL_UPDATE_ENTITY
from .entity import OVMSBaseEntity
from .metrics import (
    BINARY_METRICS,
    get_metric_by_path,
    get_metric_by_pattern,
)

_LOGGER = logging.getLogger(LOGGER_NAME)

# A mapping of binary sensor name patterns to device classes
BINARY_SENSOR_TYPES = {
    "door": BinarySensorDeviceClass.DOOR,
    "window": BinarySensorDeviceClass.WINDOW,
    "lock": BinarySensorDeviceClass.LOCK,
    "plug": BinarySensorDeviceClass.PLUG,
    "charger": BinarySensorDeviceClass.BATTERY_CHARGING,
    "charging": BinarySensorDeviceClass.BATTERY_CHARGING,
    "battery": BinarySensorDeviceClass.BATTERY,
    "motion": BinarySensorDeviceClass.MOTION,
    "connectivity": BinarySensorDeviceClass.CONNECTIVITY,
    "power": BinarySensorDeviceClass.POWER,
    "running": {
        "device_class": None,
        "icon": "mdi:car-electric",
    },
    "online": {
        "device_class": BinarySensorDeviceClass.CONNECTIVITY,
        "icon": "mdi:car-connected",
    },
    "hvac": {
        "device_class": None,
        "icon": "mdi:air-conditioner",
    }
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up OVMS binary sensors based on a config entry."""
    @callback
    def async_add_binary_sensor(data: Dict[str, Any]) -> None:
        """Add binary sensor based on discovery data."""
        if data["entity_type"] != "binary_sensor":
            return
            
        _LOGGER.info("Adding binary sensor: %s", data["name"])
        
        sensor = OVMSBinarySensor(
            data["unique_id"],
            data["name"],
            data["topic"],
            data["payload"],
            data["device_info"],
            data["attributes"],
            data.get("friendly_name"),
        )
        
        async_add_entities([sensor])
    
    # Subscribe to discovery events
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_ADD_ENTITIES, async_add_binary_sensor)
    )


class OVMSBinarySensor(OVMSBaseEntity, BinarySensorEntity):
    """Representation of an OVMS binary sensor."""
    
    def __init__(
        self,
        unique_id: str,
        name: str,
        topic: str,
        initial_state: str,
        device_info: DeviceInfo,
        attributes: Dict[str, Any],
        friendly_name: Optional[str] = None,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(unique_id, name, topic, initial_state, device_info, attributes, friendly_name)
        
        # Try to determine device class
        self._determine_device_class()
    
    def _process_initial_state(self, initial_state: Any) -> None:
        """Process the initial state."""
        self._attr_is_on = self._parse_state(initial_state)
    
    async def _handle_restore_state(self, state) -> None:
        """Handle state restore."""
        if state.state not in (None, "unavailable", "unknown"):
            self._attr_is_on = state.state == "on"
            
        # Restore attributes if available
        if state.attributes:
            # Don't overwrite entity attributes like device_class, icon
            saved_attributes = {
                k: v for k, v in state.attributes.items()
                if k not in ["device_class", "icon"]
            }
            self._attr_extra_state_attributes.update(saved_attributes)
    
    def _handle_update(self, payload: str) -> None:
        """Handle state updates."""
        self._attr_is_on = self._parse_state(payload)
        
        # Call parent method to update timestamp and process JSON
        super()._handle_update(payload)
        
        # Call write_ha_state
        self.async_write_ha_state()
    
    def _parse_state(self, state: str) -> bool:
        """Parse the state string to a boolean."""
        if state.lower() in ("true", "on", "yes", "1", "open", "locked"):
            return True
        if state.lower() in ("false", "off", "no", "0", "closed", "unlocked"):
            return False
        
        # Try numeric comparison
        try:
            return float(state) > 0
        except (ValueError, TypeError):
            return False
    
    def _determine_device_class(self) -> None:
        """Determine the device class based on metrics definitions."""
        # Default value
        self._attr_device_class = None
        self._attr_icon = None
        
        # Try to find matching metric by converting topic to dot notation
        topic_suffix = self._topic
        if self._topic.count('/') >= 3:  # Skip the prefix part
            parts = self._topic.split('/')
            # Find where the actual metric path starts
            for i, part in enumerate(parts):
                if part in ["metric", "status", "notify", "command", "m", "v", "s", "t"]:
                    topic_suffix = '/'.join(parts[i:])
                    break
        
        metric_path = topic_suffix.replace("/", ".")
        
        # Try exact match first
        metric_info = get_metric_by_path(metric_path)
        
        # If no exact match, try by pattern in name and topic
        if not metric_info:
            topic_parts = topic_suffix.split('/')
            name_parts = self._internal_name.split('_')
            metric_info = get_metric_by_pattern(topic_parts) or get_metric_by_pattern(name_parts)
        
        # Apply metric info if found
        if metric_info:
            if "device_class" in metric_info:
                self._attr_device_class = metric_info["device_class"]
            if "icon" in metric_info:
                self._attr_icon = metric_info["icon"]
            return
        
        # If no metric info was found, use the original pattern matching as fallback
        for key, device_class in BINARY_SENSOR_TYPES.items():
            if key in self._internal_name.lower():
                if isinstance(device_class, dict):
                    self._attr_device_class = device_class.get("device_class")
                    self._attr_icon = device_class.get("icon")
                else:
                    self._attr_device_class = device_class
                break
