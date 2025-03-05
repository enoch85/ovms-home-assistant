"""Support for OVMS sensors."""
import logging
import json
from datetime import datetime
from typing import Any, Dict, Optional, List

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfPower,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, LOGGER_NAME
from .mqtt import SIGNAL_ADD_ENTITIES, SIGNAL_UPDATE_ENTITY

_LOGGER = logging.getLogger(LOGGER_NAME)

# A mapping of sensor name patterns to device classes and units
SENSOR_TYPES = {
    "soc": {
        "device_class": SensorDeviceClass.BATTERY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "icon": "mdi:battery",
    },
    "range": {
        "device_class": SensorDeviceClass.DISTANCE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfLength.KILOMETERS,
        "icon": "mdi:map-marker-distance",
    },
    "temperature": {
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer",
    },
    "power": {
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
        "icon": "mdi:flash",
    },
    "current": {
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricCurrent.AMPERE,
        "icon": "mdi:current-ac",
    },
    "voltage": {
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "icon": "mdi:flash",
    },
    "energy": {
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:battery-charging",
    },
    "speed": {
        "device_class": SensorDeviceClass.SPEED,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfSpeed.KILOMETERS_PER_HOUR,
        "icon": "mdi:speedometer",
    },
    # Additional icons for EV-specific metrics
    "odometer": {
        "icon": "mdi:counter",
        "state_class": SensorStateClass.TOTAL_INCREASING,
    },
    "efficiency": {
        "icon": "mdi:leaf",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "charging_time": {
        "icon": "mdi:timer",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "climate": {
        "icon": "mdi:fan",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "hvac": {
        "icon": "mdi:air-conditioner", 
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "motor": {
        "icon": "mdi:engine",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "trip": {
        "icon": "mdi:map-marker-path",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    # Diagnostic sensors
    "status": {
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:information-outline",
    },
    "signal": {
        "entity_category": EntityCategory.DIAGNOSTIC,
        "device_class": SensorDeviceClass.SIGNAL_STRENGTH,
        "icon": "mdi:signal",
    },
    "firmware": {
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:package-up",
    },
    "version": {
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:tag-text",
    },
    "task": {
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:list-status",
    }
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up OVMS sensors based on a config entry."""
    @callback
    def async_add_sensor(data: Dict[str, Any]) -> None:
        """Add sensor based on discovery data."""
        if data["entity_type"] != "sensor":
            return
            
        _LOGGER.info("Adding sensor: %s", data["name"])
        
        sensor = OVMSSensor(
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
        async_dispatcher_connect(hass, SIGNAL_ADD_ENTITIES, async_add_sensor)
    )


class OVMSSensor(SensorEntity, RestoreEntity):
    """Representation of an OVMS sensor."""
    
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
        """Initialize the sensor."""
        self._attr_unique_id = unique_id
        # Use the entity_id compatible name for internal use
        self._internal_name = name
        # Set the entity name that will display in UI to friendly name or name
        self._attr_name = friendly_name or name.replace("_", " ").title()
        self._topic = topic
        self._attr_device_info = device_info
        self._attr_extra_state_attributes = {
            **attributes,
            "topic": topic,
            "last_updated": dt_util.utcnow().isoformat(),
        }
        
        # Try to determine device class and unit
        self._determine_sensor_type()
        
        # Only set native value after attributes are initialized
        self._attr_native_value = self._parse_value(initial_state)
        
        # Try to extract additional attributes from initial state if it's JSON
        self._process_json_payload(initial_state)
        
        # Initialize cell sensors tracking
        self._cell_sensors_created = False
        self._cell_sensors = []
        self._cell_registry = {}
        self._cell_sensor_entities = {}
    
    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        await super().async_added_to_hass()
        
        # Restore previous state if available
        if (state := await self.async_get_last_state()) is not None:
            self._attr_native_value = state.state
            # Restore attributes if available
            if state.attributes:
                # Don't overwrite entity attributes like unit, etc.
                saved_attributes = {
                    k: v for k, v in state.attributes.items()
                    if k not in ["device_class", "state_class", "unit_of_measurement"]
                }
                self._attr_extra_state_attributes.update(saved_attributes)
        
        @callback
        def update_state(payload: str) -> None:
            """Update the sensor state."""
            self._attr_native_value = self._parse_value(payload)
            
            # Update timestamp attribute
            now = dt_util.utcnow()
            self._attr_extra_state_attributes["last_updated"] = now.isoformat()
            
            # Try to extract additional attributes from payload if it's JSON
            self._process_json_payload(payload)
            
            self.async_write_ha_state()
            
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_UPDATE_ENTITY}_{self.unique_id}",
                update_state,
            )
        )
    
    def _determine_sensor_type(self) -> None:
        """Determine the sensor type based on name patterns."""
        # Default values
        self._attr_device_class = None
        self._attr_state_class = None
        self._attr_native_unit_of_measurement = None
        self._attr_entity_category = None
        self._attr_icon = None
        
        # Check for matching patterns in name
        for key, sensor_type in SENSOR_TYPES.items():
            if key in self._internal_name.lower() or key in self._topic.lower():
                self._attr_device_class = sensor_type.get("device_class")
                self._attr_state_class = sensor_type.get("state_class")
                self._attr_native_unit_of_measurement = sensor_type.get("unit")
                self._attr_entity_category = sensor_type.get("entity_category")
                self._attr_icon = sensor_type.get("icon")
                break
    
    def _parse_value(self, value: str) -> Any:
        """Parse the value from the payload."""
        # Check if this is a comma-separated list of numbers (including negative numbers)
        if isinstance(value, str) and "," in value:
            try:
                # Try to parse all parts as floats
                parts = [float(part.strip()) for part in value.split(",") if part.strip()]
                if parts:
                    # Store the array in attributes
                    self._attr_extra_state_attributes["cell_values"] = parts
                    self._attr_extra_state_attributes["cell_count"] = len(parts)
                    
                    # Create individual cell sensors if they don't exist yet
                    self._create_cell_sensors(parts)
                    
                    # Calculate and return average value
                    avg_value = sum(parts) / len(parts)
                    return avg_value
            except (ValueError, TypeError):
                # If any part can't be converted to float, fall through to other methods
                pass
        
        # Rest of the original parsing logic follows...
        try:
            # Try parsing as JSON first
            json_val = json.loads(value)
            
            # If JSON is a dict, extract likely value
            if isinstance(json_val, dict):
                if "value" in json_val:
                    return json_val["value"]
                if "state" in json_val:
                    return json_val["state"]
                # Return first numeric value found
                for key, val in json_val.items():
                    if isinstance(val, (int, float)):
                        return val
                # Fall back to string representation
                return str(json_val)
            
            # If JSON is a scalar, use it directly
            if isinstance(json_val, (int, float, str, bool)):
                return json_val
                
            # For arrays or other types, convert to string
            return str(json_val)
            
        except (ValueError, json.JSONDecodeError):
            # Not JSON, try numeric
            try:
                # Check if it's a float
                if "." in value:
                    return float(value)
                # Check if it's an int
                return int(value)
            except (ValueError, TypeError):
                # Return as string
                return value
    
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
                    
                # If there's a unit in the JSON, use it for native unit
                if "unit" in json_data and not self._attr_native_unit_of_measurement:
                    unit = json_data["unit"]
                    self._attr_native_unit_of_measurement = unit
                    
        except (ValueError, json.JSONDecodeError):
            # Not JSON, that's fine
            pass
            
    def _create_cell_sensors(self, cell_values):
        """Create individual sensors for each cell value."""
        # Only create cell sensors if we haven't done so already
        if hasattr(self, '_cell_sensors_created') and self._cell_sensors_created:
            # If we already created them, just update their values
            self._update_cell_sensor_values(cell_values)
            return
            
        from homeassistant.helpers.entity import async_generate_entity_id
        from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
        
        # Get base information to create child sensors
        base_name = self._internal_name  # Use internal name for entity_id
        # Get readable base name for friendly names from attribute name
        friendly_base_name = self.name  # Use the friendly name for display
        
        # Clean "voltage" from the name to avoid duplication
        base_name = base_name.replace("voltage", "").replace("Voltage", "").strip()
        base_name = base_name.rstrip("_").strip()
        
        # Get vehicle ID from unique_id for prefixing
        vehicle_id = self.unique_id.split("_")[0]
        
        self._cell_sensors = []
        registry = {}
        
        # Create a sensor for each cell
        for i, value in enumerate(cell_values):
            # Create unique ID for this cell sensor
            cell_unique_id = f"{self.unique_id}_cell_{i+1}"
            
            # Create entity ID with vehicle prefix
            entity_id_name = f"{vehicle_id}_{base_name}_cell_{i+1}"
            
            # Generate entity ID
            entity_id = async_generate_entity_id(
                SENSOR_DOMAIN + ".{}", 
                entity_id_name,
                hass=self.hass
            )
            
            # Create friendly name for cell
            friendly_name = f"{friendly_base_name} Cell {i+1}"
            
            # Create a sensor configuration to register later
            sensor_config = {
                "unique_id": cell_unique_id,
                "name": entity_id_name,
                "friendly_name": friendly_name,
                "state": value,
                "entity_id": entity_id,
                "device_info": self.device_info,
                "device_class": self.device_class,
                "state_class": SensorStateClass.MEASUREMENT,
                "unit_of_measurement": self.native_unit_of_measurement,
                "cell_index": i,
            }
            
            # Register this cell sensor
            registry[cell_unique_id] = sensor_config
            self._cell_sensors.append(cell_unique_id)
        
        # Store in class attribute for future updates
        self._cell_registry = registry
        self._cell_sensors_created = True
        
        # Schedule registration of these sensors
        if self.hass:
            async_call_later(self.hass, 0, self._register_cell_sensors)

    async def _register_cell_sensors(self, _now=None):
        """Register the cell sensors in Home Assistant."""
        if not hasattr(self, '_cell_registry') or not self._cell_registry:
            return
            
        from homeassistant.helpers.entity import Entity
        
        # Create a custom sensor class for the cell sensors
        class CellVoltageSensor(SensorEntity, RestoreEntity):
            """Representation of a cell voltage sensor."""
            
            def __init__(self, config):
                """Initialize the sensor."""
                self._attr_unique_id = config["unique_id"]
                self._internal_name = config["name"]
                self._attr_name = config["friendly_name"]
                self._attr_native_value = config["state"]
                self._attr_device_info = config["device_info"]
                self._attr_device_class = config["device_class"]
                self._attr_state_class = config["state_class"]
                self._attr_native_unit_of_measurement = config["unit_of_measurement"]
                self.entity_id = config["entity_id"]
                self.cell_index = config["cell_index"]
        
        # Create and add all cell sensors
        entities = []
        for sensor_id, config in self._cell_registry.items():
            sensor = CellVoltageSensor(config)
            entities.append(sensor)
        
        # Add entities to Home Assistant
        if entities:
            try:
                # Add entities to Home Assistant
                async_add_entities = self.platform.async_add_entities
                async_add_entities(entities)
            except (AttributeError, NameError):
                _LOGGER.warning("Failed to register cell sensors through platform")
                try:
                    # Alternative approach if platform isn't available
                    from homeassistant.helpers.entity_component import EntityComponent
                    component = self.hass.data.get('entity_components', {}).get('sensor')
                    if component and isinstance(component, EntityComponent):
                        await component.async_add_entities(entities)
                    else:
                        _LOGGER.warning("Failed to find sensor component for adding entities")
                except Exception as ex:
                    _LOGGER.exception("Error registering cell sensors: %s", ex)
            
        # Store entities for future updates
        self._cell_sensor_entities = {e.unique_id: e for e in entities}

    def _update_cell_sensor_values(self, cell_values):
        """Update the values of existing cell sensors."""
        if not hasattr(self, '_cell_sensor_entities') or not self._cell_sensor_entities:
            return
            
        # Update each cell sensor with its new value
        for i, value in enumerate(cell_values):
            if i < len(self._cell_sensors):
                cell_id = self._cell_sensors[i]
                if cell_id in self._cell_sensor_entities:
                    entity = self._cell_sensor_entities[cell_id]
                    entity._attr_native_value = value
                    
                    # Schedule an update for this entity
                    if self.hass:
                        entity.async_schedule_update_ha_state()