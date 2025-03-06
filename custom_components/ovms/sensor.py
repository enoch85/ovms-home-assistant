"""Support for OVMS sensors."""
import logging
import json
import re
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
from homeassistant.util import dt as dt_util

from .const import DOMAIN, LOGGER_NAME
from .mqtt import SIGNAL_ADD_ENTITIES, SIGNAL_UPDATE_ENTITY
from .entity import OVMSBaseEntity
from .metrics import (
    METRIC_DEFINITIONS,
    TOPIC_PATTERNS,
    get_metric_by_path,
    get_metric_by_pattern,
)

_LOGGER = logging.getLogger(LOGGER_NAME)

# List of device classes that should have numeric values
NUMERIC_DEVICE_CLASSES = [
    SensorDeviceClass.BATTERY,
    SensorDeviceClass.CURRENT,
    SensorDeviceClass.ENERGY,
    SensorDeviceClass.HUMIDITY,
    SensorDeviceClass.POWER,
    SensorDeviceClass.TEMPERATURE,
    SensorDeviceClass.VOLTAGE,
    SensorDeviceClass.DISTANCE,
    SensorDeviceClass.SPEED,
]


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


class OVMSSensor(OVMSBaseEntity, SensorEntity):
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
        super().__init__(unique_id, name, topic, initial_state, device_info, attributes, friendly_name)
        
        # Try to determine device class and unit
        self._determine_sensor_type()
        
        # Initialize cell sensors tracking
        self._cell_sensors_created = False
        self._cell_sensors = []
        self._cell_registry = {}
        self._cell_sensor_entities = {}
        
    def _process_initial_state(self, initial_state: Any) -> None:
        """Process the initial state."""
        # Only set native value after attributes are initialized
        self._attr_native_value = self._parse_value(initial_state)
        
        # Try to extract additional attributes from initial state if it's JSON
        self._process_json_payload(initial_state)
    
    async def _handle_restore_state(self, state) -> None:
        """Handle state restore."""
        if state.state not in ["unavailable", "unknown", None]:
            # Only restore the state if it's not a special state
            self._attr_native_value = state.state
        # Restore attributes if available
        if state.attributes:
            # Don't overwrite entity attributes like unit, etc.
            saved_attributes = {
                k: v for k, v in state.attributes.items()
                if k not in ["device_class", "state_class", "unit_of_measurement"]
            }
            self._attr_extra_state_attributes.update(saved_attributes)
    
    def _handle_update(self, payload: str) -> None:
        """Handle state updates."""
        self._attr_native_value = self._parse_value(payload)
        
        # Update timestamp attribute
        now = dt_util.utcnow()
        self._attr_extra_state_attributes["last_updated"] = now.isoformat()
        
        # Try to extract additional attributes from payload if it's JSON
        self._process_json_payload(payload)
        
        self.async_write_ha_state()
    
    def _determine_sensor_type(self) -> None:
        """Determine the sensor type based on metrics definitions."""
        # Default values
        self._attr_device_class = None
        self._attr_state_class = None
        self._attr_native_unit_of_measurement = None
        self._attr_entity_category = None
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
            if "state_class" in metric_info:
                self._attr_state_class = metric_info["state_class"]
            if "unit" in metric_info:
                self._attr_native_unit_of_measurement = metric_info["unit"]
            if "entity_category" in metric_info:
                self._attr_entity_category = metric_info["entity_category"]
            if "icon" in metric_info:
                self._attr_icon = metric_info["icon"]
    
    def _requires_numeric_value(self) -> bool:
        """Check if this sensor requires a numeric value based on its device class."""
        return (
            self._attr_device_class in NUMERIC_DEVICE_CLASSES or
            self._attr_state_class in [SensorStateClass.MEASUREMENT, SensorStateClass.TOTAL, SensorStateClass.TOTAL_INCREASING]
        )
        
    def _parse_value(self, value: Any) -> Any:
        """Parse the value from the payload."""
        # Handle special state values for numeric sensors
        if self._requires_numeric_value() and self._is_special_state_value(value):
            return None
            
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
            
            # Handle special JSON values
            if self._is_special_state_value(json_val):
                return None
                
            # If JSON is a dict, extract likely value
            if isinstance(json_val, dict):
                result = None
                if "value" in json_val:
                    result = json_val["value"]
                elif "state" in json_val:
                    result = json_val["state"]
                else:
                    # Return first numeric value found
                    for key, val in json_val.items():
                        if isinstance(val, (int, float)):
                            result = val
                            break
                
                # Handle special values in result
                if self._is_special_state_value(result):
                    return None
                    
                # If we have a result, return it; otherwise fall back to string representation
                if result is not None:
                    return result
                
                # If we need a numeric value but couldn't extract one, return None
                if self._requires_numeric_value():
                    return None
                return str(json_val)
            
            # If JSON is a scalar, use it directly
            if isinstance(json_val, (int, float)):
                return json_val
            
            if isinstance(json_val, str):
                # Handle special string values
                if self._is_special_state_value(json_val):
                    return None
                    
                # If we need a numeric value but got a string, try to convert it
                if self._requires_numeric_value():
                    try:
                        return float(json_val)
                    except (ValueError, TypeError):
                        return None
                return json_val
                
            if isinstance(json_val, bool):
                # If we need a numeric value, convert bool to int
                if self._requires_numeric_value():
                    return 1 if json_val else 0
                return json_val
                
            # For arrays or other types, convert to string if not numeric
            if self._requires_numeric_value():
                return None
            return str(json_val)
            
        except (ValueError, json.JSONDecodeError):
            # Not JSON, try numeric
            try:
                # Check if it's a float
                if isinstance(value, str) and "." in value:
                    return float(value)
                # Check if it's an int
                return int(value)
            except (ValueError, TypeError):
                # If we need a numeric value but couldn't convert, return None
                if self._requires_numeric_value():
                    return None
                # Otherwise return as string
                return value
    
    def _process_entity_name(self, vehicle_id, metric_path):
        """Process entity name to avoid duplications."""
        # Clean up any instances of vehicle_id in metric_path
        if vehicle_id.lower() in metric_path.lower():
            cleaned_path = re.sub(
                f"(?i){re.escape(vehicle_id)}_*", 
                "", 
                metric_path
            ).strip("_")
            return f"ovms_{vehicle_id}_{cleaned_path}" if cleaned_path else f"ovms_{vehicle_id}"
        else:
            return f"ovms_{vehicle_id}_{metric_path}"
            
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
            # Create unique ID for this cell sensor using the helper method
            # First, create a clean unique ID for the parent
            clean_parent_id = self._process_entity_name(vehicle_id, self.unique_id)
            cell_unique_id = f"{clean_parent_id}_cell_{i+1}"
            
            # Use helper method for entity ID name too
            entity_id_name = self._process_entity_name(vehicle_id, f"{base_name}_cell_{i+1}")
            
            # Generate entity ID
            entity_id = async_generate_entity_id(
                SENSOR_DOMAIN + ".{}", 
                entity_id_name.lower(),
                hass=self.hass
            )
            
            # Create friendly name for cell
            friendly_name = f"{friendly_base_name} Cell {i+1}"
            
            # Ensure value is numeric for sensors with device class
            if self._requires_numeric_value() and self._is_special_state_value(value):
                parsed_value = None
            else:
                parsed_value = value
            
            # Create a sensor configuration to register later
            sensor_config = {
                "unique_id": cell_unique_id,
                "name": entity_id_name,
                "friendly_name": friendly_name,
                "state": parsed_value,
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
        class CellSensor(OVMSBaseEntity, SensorEntity):
            """Representation of a cell sensor."""
            
            def __init__(self, config):
                """Initialize the sensor."""
                # Extract base entity attributes from config
                unique_id = config["unique_id"]
                name = config["name"]
                # There's no topic for cell sensors, but we need something unique
                topic = f"cell_sensor/{unique_id}"  
                initial_state = config["state"]
                device_info = config["device_info"]
                attributes = {
                    "cell_index": config["cell_index"],
                    "parent_entity": self.entity_id,
                }
                friendly_name = config["friendly_name"]
                
                # Initialize base entity
                super().__init__(
                    unique_id, name, topic, initial_state, 
                    device_info, attributes, friendly_name
                )
                
                # Set specific entity attributes
                self._attr_device_class = config["device_class"]
                self._attr_state_class = config["state_class"]
                self._attr_native_unit_of_measurement = config["unit_of_measurement"]
                self.entity_id = config["entity_id"]
                
                # Set native value explicitly since we're not using _process_initial_state
                self._attr_native_value = initial_state
        
        # Create and add all cell sensors
        entities = []
        for sensor_id, config in self._cell_registry.items():
            sensor = CellSensor(config)
            entities.append(sensor)
        
        # Add entities to Home Assistant
        if entities:
            try:
                # Add entities to Home Assistant
                async_add_entities = self.platform.async_add_entities
                await self.hass.async_add_executor_job(async_add_entities, entities)
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
                    
                    # Ensure value is numeric for sensors with device class
                    if hasattr(entity, '_attr_device_class') and entity._attr_device_class in NUMERIC_DEVICE_CLASSES:
                        if isinstance(value, str) and value.lower() in ["unavailable", "unknown", "none", "", "null", "nan"]:
                            entity._attr_native_value = None
                        else:
                            try:
                                entity._attr_native_value = float(value)
                            except (ValueError, TypeError):
                                entity._attr_native_value = None
                    else:
                        entity._attr_native_value = value
                    
                    # Schedule an update for this entity
                    if self.hass:
                        try:
                            entity.async_schedule_update_ha_state()
                        except RuntimeError as e:
                            if "Attribute hass is None" in str(e):
                                _LOGGER.debug("Cell sensor entity not ready for update: %s", e)
                            else:
                                raise
