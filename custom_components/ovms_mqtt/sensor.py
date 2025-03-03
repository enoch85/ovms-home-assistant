"""OVMS MQTT sensor platform."""
import logging
from typing import Any, Dict, Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import SensorEntity

from .const import (
    DOMAIN,
    CONF_TOPIC_PREFIX,
    CONF_VEHICLE_ID,
    DEFAULT_TOPIC_PREFIX,
    DEFAULT_VEHICLE_ID,
)
from .mqtt_handler import async_setup_mqtt_handler
from .entity_handler import get_vehicle_device_info, get_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> bool:
    """Set up OVMS MQTT sensor based on a config entry."""
    _LOGGER.debug("Setting up OVMS MQTT sensor platform")
    
    # Extract configuration
    config = entry.data
    topic_prefix = config.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
    vehicle_id = config.get(CONF_VEHICLE_ID, DEFAULT_VEHICLE_ID)

    # Set up MQTT handler
    mqtt_handler = await async_setup_mqtt_handler(hass, entry)
    if not mqtt_handler:
        _LOGGER.error("Failed to set up MQTT handler")
        return False

    # Store config and entities in hass.data if not already present
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    
    if entry.entry_id not in hass.data[DOMAIN]:
        hass.data[DOMAIN][entry.entry_id] = {
            "entities": {},
            "config": config,
            "data_handler": mqtt_handler,
        }

    # Set up platform with entity tracking
    platform = OVMSSensorPlatform(hass, entry, async_add_entities)
    await platform.async_setup()
    
    return True


class OVMSSensorPlatform:
    """Manage OVMS entities through dispatchers."""

    def __init__(
        self, 
        hass: HomeAssistant, 
        entry: ConfigEntry, 
        async_add_entities: AddEntitiesCallback
    ) -> None:
        """Initialize the platform."""
        self.hass = hass
        self.entry = entry
        self.entry_id = entry.entry_id
        self.async_add_entities = async_add_entities
        self.added_entities: Dict[str, OVMSSensor] = {}
        self._remove_signal_handlers: list[Callable[[], None]] = []

    async def async_setup(self) -> None:
        """Set up the platform handlers."""
        # Listen for new entities
        self._remove_signal_handlers.append(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_{self.entry_id}_new_entity",
                self.async_add_new_entity
            )
        )

        # Listen for entity updates
        self._remove_signal_handlers.append(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_{self.entry_id}_state_update",
                self.async_update_entity
            )
        )

    async def async_unload(self) -> None:
        """Unload the platform handlers."""
        # Remove dispatcher connections
        for remove_handler in self._remove_signal_handlers:
            remove_handler()
        self._remove_signal_handlers = []

    @callback
    def async_add_new_entity(self, unique_id: str) -> None:
        """Add a new entity."""
        if unique_id in self.added_entities:
            return

        # Get entity data
        entity_data = self.hass.data[DOMAIN][self.entry_id]["entities"].get(unique_id)
        if not entity_data:
            _LOGGER.warning("Entity data not found for unique_id: %s", unique_id)
            return

        # Create the sensor entity
        sensor = OVMSSensor(self.hass, self.entry_id, unique_id, entity_data)
        self.added_entities[unique_id] = sensor
        
        # Add entity to HA
        _LOGGER.debug("Adding new entity: %s", unique_id)
        self.async_add_entities([sensor])

    @callback
    def async_update_entity(self, unique_id: str) -> None:
        """Update an entity state."""
        if unique_id not in self.added_entities:
            # If the entity doesn't exist yet, add it
            self.async_add_new_entity(unique_id)
            return

        # Trigger state update
        entity = self.added_entities[unique_id]
        entity.async_schedule_update_ha_state()


class OVMSSensor(SensorEntity):
    """Representation of an OVMS MQTT sensor."""

    def __init__(
        self, 
        hass: HomeAssistant, 
        entry_id: str, 
        unique_id: str,
        entity_data: Dict[str, Any]
    ) -> None:
        """Initialize the sensor."""
        self.hass = hass
        self.entry_id = entry_id
        self._unique_id = unique_id
        self._topic = entity_data.get("topic", "")
        self._vehicle_id = entity_data.get("vehicle_id", "")
        self._category = entity_data.get("category")
        
        # Entity attributes
        self._attr_unique_id = unique_id
        self._attr_name = entity_data.get("name")
        self._attr_native_value = entity_data.get("state")
        self._attr_native_unit_of_measurement = entity_data.get("unit")
        self._attr_device_class = entity_data.get("device_class")
        self._attr_state_class = entity_data.get("state_class")
        self._attr_icon = entity_data.get("icon")
        self._attr_available = entity_data.get("available", True)
        
        # Set up device info based on topic category
        if self._category:
            self._attr_device_info = get_device_info(self._vehicle_id, self._category)
        else:
            self._attr_device_info = get_vehicle_device_info(self._vehicle_id)

        _LOGGER.debug(
            "Initialized sensor %s: name=%s, value=%s, device_class=%s",
            unique_id, self._attr_name, self._attr_native_value, self._attr_device_class
        )

    @property
    def should_poll(self) -> bool:
        """No polling needed for MQTT sensors."""
        return False

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        entity_data = self.hass.data[DOMAIN][self.entry_id]["entities"].get(self._unique_id)
        if not entity_data:
            return
        
        self._attr_native_value = entity_data.get("state")
        self._attr_native_unit_of_measurement = entity_data.get("unit", self._attr_native_unit_of_measurement)
        self._attr_icon = entity_data.get("icon", self._attr_icon)
        self._attr_available = entity_data.get("available", True)
        
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        # Add dispatcher listener for state updates
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_{self.entry_id}_state_update",
                self._async_handle_update
            )
        )

    @callback
    def _async_handle_update(self, unique_id: str) -> None:
        """Update state."""
        if unique_id != self._unique_id:
            return
        
        # Update state from entity_data
        self._handle_coordinator_update()
