"""Sensor platform for OVMS MQTT integration."""
import logging
from typing import Optional, Dict, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import slugify

from .const import DOMAIN, DEFAULT_MANUFACTURER, CONF_VEHICLE_ID, DEFAULT_VEHICLE_ID

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up OVMS MQTT sensors based on a config entry."""
    _LOGGER.debug(f"Setting up OVMS MQTT sensor platform for entry {entry.entry_id}")
    
    # Get stored entities from hass.data
    entities = hass.data[DOMAIN][entry.entry_id]["entities"]
    vehicle_id = entry.data.get(CONF_VEHICLE_ID, DEFAULT_VEHICLE_ID)
    
    # Add entities for existing data
    sensors = []
    for entity_id, entity_data in entities.items():
        _LOGGER.debug(f"Creating sensor for existing entity: {entity_id}")
        sensors.append(
            OVMSMQTTSensor(
                hass,
                entry,
                entity_id,
                entity_data["topic"],
                entity_data["name"],
                entity_data.get("unique_id", entity_id),
                vehicle_id,
            )
        )
    
    if sensors:
        async_add_entities(sensors)
    
    @callback
    def async_add_sensor(entity_id):
        """Add sensor for a newly received MQTT topic."""
        _LOGGER.debug(f"Adding new sensor for entity: {entity_id}")
        if entity_id in entities:
            entity_data = entities[entity_id]
            sensor = OVMSMQTTSensor(
                hass,
                entry,
                entity_id,
                entity_data["topic"],
                entity_data["name"],
                entity_data.get("unique_id", entity_id),
                vehicle_id,
            )
            async_add_entities([sensor])
    
    # Connect to dispatcher to add new sensors
    entry.async_on_unload(
        async_dispatcher_connect(
            hass, f"{DOMAIN}_{entry.entry_id}_new_entity", async_add_sensor
        )
    )


class OVMSMQTTSensor(SensorEntity):
    """Representation of an OVMS MQTT sensor."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        entity_id: str,
        topic: str,
        name: str,
        unique_id: str,
        vehicle_id: str,
    ) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self.entry = entry
        self._entity_id = entity_id
        self.topic = topic
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._vehicle_id = vehicle_id
        
        # Get last component of the topic for device class guessing
        topic_parts = topic.split('/')
        self._topic_last_part = topic_parts[-1] if topic_parts else ""
        
        # Guess device class and unit based on topic
        self._attr_device_class = self._guess_device_class()
        self._attr_native_unit_of_measurement = self._guess_unit()
        
        # Device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._vehicle_id)},
            name=f"OVMS Vehicle {self._vehicle_id}",
            manufacturer=DEFAULT_MANUFACTURER,
            model="OVMS",
        )
        
        _LOGGER.debug(
            f"Initialized sensor: {self._attr_name} (ID: {self._entity_id}) "
            f"with device class: {self._attr_device_class}, "
            f"unit: {self._attr_native_unit_of_measurement}"
        )

    def _guess_device_class(self) -> Optional[str]:
        """Guess device class based on topic/name."""
        topic_lower = self._topic_last_part.lower()
        
        if "temp" in topic_lower:
            return "temperature"
        elif "humidity" in topic_lower:
            return "humidity"
        elif "soc" in topic_lower or "battery" in topic_lower:
            return "battery"
        elif "voltage" in topic_lower:
            return "voltage"
        elif "current" in topic_lower:
            return "current"
        elif "power" in topic_lower:
            return "power"
        elif "energy" in topic_lower:
            return "energy"
        elif "distance" in topic_lower or "odometer" in topic_lower:
            return "distance"
        elif "speed" in topic_lower:
            return "speed"
        
        return None

    def _guess_unit(self) -> str:
        """Guess unit based on topic/name and device class."""
        topic_lower = self._topic_last_part.lower()
        
        if self._attr_device_class == "temperature":
            return "°C"
        elif self._attr_device_class == "humidity":
            return "%"
        elif self._attr_device_class == "battery":
            return "%"
        elif self._attr_device_class == "voltage":
            return "V"
        elif self._attr_device_class == "current":
            return "A"
        elif self._attr_device_class == "power":
            return "W"
        elif self._attr_device_class == "energy":
            return "kWh"
        elif self._attr_device_class == "distance":
            return "km"
        elif self._attr_device_class == "speed":
            return "km/h"
        
        # Check topic for unit hints
        if "percent" in topic_lower or "%" in topic_lower:
            return "%"
        elif "temp" in topic_lower:
            return "°C"
        
        return ""

    async def async_added_to_hass(self) -> None:
        """Subscribe to state updates."""
        await super().async_added_to_hass()
        
        # Subscribe to state updates
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_{self.entry.entry_id}_state_update",
                self._handle_state_update,
            )
        )
        
        # Set initial state
        self._update_state()

    @callback
    def _handle_state_update(self, entity_id):
        """Handle state update from dispatcher."""
        if entity_id == self._entity_id:
            self._update_state()
            self.async_write_ha_state()

    def _update_state(self):
        """Update state from MQTT data."""
        entity_data = self.hass.data[DOMAIN][self.entry.entry_id]["entities"].get(self._entity_id)
        if entity_data:
            state_value = entity_data.get("state")
            
            # Convert boolean values to "ON"/"OFF" strings
            if isinstance(state_value, bool):
                self._attr_native_value = "ON" if state_value else "OFF"
            else:
                self._attr_native_value = state_value
                
            # Update unit if available
            if "unit" in entity_data and entity_data["unit"]:
                self._attr_native_unit_of_measurement = entity_data["unit"]

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._entity_id in self.hass.data[DOMAIN][self.entry.entry_id]["entities"]
