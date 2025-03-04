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

_LOGGER = logging.getLogger(LOGGER_NAME)

# A mapping of binary sensor name patterns to device classes
BINARY_SENSOR_TYPES = {
    "door": BinarySensorDeviceClass.DOOR,
    "window": BinarySensorDeviceClass.WINDOW,
    "lock": BinarySensorDeviceClass.LOCK,
    "plug": BinarySensorDeviceClass.PLUG,
    "charger": BinarySensorDeviceClass.BATTERY_CHARGING,
    "battery": BinarySensorDeviceClass.BATTERY,
    "motion": BinarySensorDeviceClass.MOTION,
    "connectivity": BinarySensorDeviceClass.CONNECTIVITY,
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
        )
        
        async_add_entities([sensor])
    
    # Subscribe to discovery events
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_ADD_ENTITIES, async_add_binary_sensor)
    )


class OVMSBinarySensor(BinarySensorEntity):
    """Representation of an OVMS binary sensor."""
    
    def __init__(
        self,
        unique_id: str,
        name: str,
        topic: str,
        initial_state: str,
        device_info: DeviceInfo,
        attributes: Dict[str, Any],
    ) -> None:
        """Initialize the binary sensor."""
        self._attr_unique_id = unique_id
        self._attr_name = name
        self._topic = topic
        self._attr_is_on = self._parse_state(initial_state)
        self._attr_device_info = device_info
        self._attr_extra_state_attributes = attributes
        
        # Try to determine device class
        self._determine_device_class()
    
    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        @callback
        def update_state(payload: str) -> None:
            """Update the sensor state."""
            self._attr_is_on = self._parse_state(payload)
            self.async_write_ha_state()
            
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_UPDATE_ENTITY}_{self.unique_id}",
                update_state,
            )
        )
    
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
        """Determine the device class based on name patterns."""
        # Default value
        self._attr_device_class = None
        
        # Check for matching patterns in name
        for key, device_class in BINARY_SENSOR_TYPES.items():
            if key in self._attr_name.lower():
                self._attr_device_class = device_class
                break
