"""Sensor platform for OVMS MQTT integration."""
from __future__ import annotations

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    CONF_AVAILABILITY_TIMEOUT,
    DEFAULT_AVAILABILITY_TIMEOUT,
)
from .entity_handler import get_device_info, get_vehicle_device_info, get_battery_icon

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up OVMS MQTT sensors based on a config entry."""
    _LOGGER.debug("Setting up OVMS MQTT sensor platform for entry %s", entry.entry_id)
    
    # Get stored entities from hass.data
    if entry.entry_id not in hass.data[DOMAIN]:
        _LOGGER.warning("Config entry %s not found in hass.data", entry.entry_id)
        return
    
    entities_data = hass.data[DOMAIN][entry.entry_id].get("entities", {})
    
    # Create entities for existing data
    sensors = []
    entity_ids_created = set()
    
    for unique_id, entity_data in entities_data.items():
        if unique_id in entity_ids_created:
            continue
            
        sensor = OVMSMQTTSensor(hass, entry, unique_id, entity_data)
        sensors.append(sensor)
        entity_ids_created.add(unique_id)
    
    if sensors:
        async_add_entities(sensors)
    
    @callback
    def async_add_sensor(unique_id):
        """Add sensor for a newly received MQTT topic."""
        if unique_id in entity_ids_created:
            return
            
        entity_data = hass.data[DOMAIN][entry.entry_id]["entities"].get(unique_id)
        if not entity_data:
            return
            
        sensor = OVMSMQTTSensor(hass, entry, unique_id, entity_data)
        async_add_entities([sensor])
        entity_ids_created.add(unique_id)
    
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
        config_entry: ConfigEntry,
        unique_id: str,
        entity_data: Dict,
    ) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self.config_entry = config_entry
        self._unique_id = unique_id
        self._attr_unique_id = unique_id
        self._attr_available = True  # Initially assume available
        self._last_updated = None
        
        # Set up various attributes from entity_data
        self._vehicle_id = entity_data.get("vehicle_id")
        self._topic = entity_data.get("topic", "")
        self._category = entity_data.get("category")
        
        # Entity attributes
        self._attr_name = entity_data.get("name")
        self._attr_native_unit_of_measurement = entity_data.get("unit")
        self._attr_device_class = entity_data.get("device_class")
        self._attr_state_class = entity_data.get("state_class")
        self._attr_icon = entity_data.get("icon")
        self._attr_native_value = entity_data.get("state")
        
        # Update last updated timestamp if available
        if "last_updated" in entity_data:
            try:
                self._last_updated = datetime.fromisoformat(entity_data["last_updated"])
            except (ValueError, TypeError):
                self._last_updated = datetime.now()
        
        # Set up device info - group by category
        if self._category and self._vehicle_id:
            self._attr_device_info = get_device_info(
                self._vehicle_id, self._category
            )
        else:
            # Fallback to main vehicle device
            self._attr_device_info = get_vehicle_device_info(self._vehicle_id)
        
        _LOGGER.debug(
            "Initialized sensor: %s (ID: %s) with device class: %s, unit: %s",
            self._attr_name,
            self._attr_unique_id,
            self._attr_device_class,
            self._attr_native_unit_of_measurement,
        )
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional attributes about the sensor."""
        attributes = {}
        
        # Add topic for debugging
        attributes["mqtt_topic"] = self._topic
        
        # Add last updated timestamp
        if self._last_updated:
            attributes["last_updated"] = self._last_updated.isoformat()
        
        return attributes

    async def async_added_to_hass(self) -> None:
        """Subscribe to state updates."""
        await super().async_added_to_hass()
        
        # Subscribe to state updates
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_{self.config_entry.entry_id}_state_update",
                self._handle_state_update,
            )
        )

    @callback
    def _handle_state_update(self, unique_id):
        """Handle state update from dispatcher."""
        if unique_id == self._unique_id:
            self._update_state()
            self.async_write_ha_state()

    def _update_state(self):
        """Update state from stored data."""
        entity_data = (
            self.hass.data[DOMAIN][self.config_entry.entry_id]["entities"].get(
                self._unique_id
            )
        )
        if entity_data:
            # Update state value
            self._attr_native_value = entity_data.get("state")
            
            # Update availability if explicitly set
            if "available" in entity_data:
                self._attr_available = entity_data["available"]
            
            # Update last updated timestamp
            if "last_updated" in entity_data:
                try:
                    self._last_updated = datetime.fromisoformat(
                        entity_data["last_updated"]
                    )
                except (ValueError, TypeError):
                    self._last_updated = datetime.now()
            
            # Update battery icon based on state if applicable
            if "soc" in self._topic and isinstance(self._attr_native_value, (int, float)):
                self._attr_icon = get_battery_icon(self._attr_native_value)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Check if entity exists in data store
        has_entity = (
            self._unique_id in
            self.hass.data[DOMAIN][self.config_entry.entry_id]["entities"]
        )
        
        if not has_entity:
            return False
            
        # If explicitly marked as unavailable
        if hasattr(self, "_attr_available") and not self._attr_available:
            return False
            
        # Check for timeout if configured
        availability_timeout = self.config_entry.data.get(
            CONF_AVAILABILITY_TIMEOUT, DEFAULT_AVAILABILITY_TIMEOUT
        )
        if availability_timeout > 0 and self._last_updated:
            # Check if last update is too old
            timeout_delta = timedelta(seconds=availability_timeout)
            if datetime.now() - self._last_updated > timeout_delta:
                return False
                
        return True
