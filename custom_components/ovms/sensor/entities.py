"""OVMS sensor entities with standardized attributes."""
import logging
from typing import Any, Dict, Optional, List
from datetime import datetime

from homeassistant.components.sensor import SensorEntity, SensorStateClass, SensorDeviceClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from ..const import DOMAIN, LOGGER_NAME, SIGNAL_ADD_ENTITIES, SIGNAL_UPDATE_ENTITY, truncate_state_value
from .parsers import parse_value, process_json_payload, requires_numeric_value, is_special_state_value, calculate_median
from .factory import determine_sensor_type, add_device_specific_attributes, create_cell_sensors
from .duration_formatter import format_duration, parse_duration

_LOGGER = logging.getLogger(LOGGER_NAME)

# Default setting for creating individual cell sensors
CREATE_INDIVIDUAL_CELL_SENSORS = False

def format_sensor_value(value, device_class, attributes):
    """Format sensor value based on device class, returns formatted value."""
    if value is None:
        return None
        
    # Clean up any potentially inconsistent attributes for all sensors
    for attr in ["formatted_value", "formatted_duration", "timestamp_iso"]:
        if attr in attributes:
            del attributes[attr]
            
    if device_class == SensorDeviceClass.DURATION:
        # For duration, store raw value and formatted value
        attributes["raw_value"] = value
        attributes["formatted_value"] = format_duration(value)
        return format_duration(value)
    elif device_class == SensorDeviceClass.TIMESTAMP:
        # For timestamp, store datetime object and formatted value
        attributes["raw_value"] = value
        if isinstance(value, datetime):
            formatted = value.isoformat()
            # Make it more readable by just keeping date and time
            if 'T' in formatted:
                date_part, time_part = formatted.split('T')
                time_part = time_part.split('+')[0].split('.')[0]
                formatted_string = f"{date_part} at {time_part}"
            else:
                formatted_string = formatted
            attributes["formatted_value"] = formatted_string
            return formatted_string
        formatted_string = str(value)
        attributes["formatted_value"] = formatted_string
        return formatted_string
    else:
        # For all other sensor types, also store raw and formatted values
        attributes["raw_value"] = value
        formatted = truncate_state_value(value)
        attributes["formatted_value"] = formatted
        return formatted

def standardize_attributes(attributes):
    """Standardize attributes across all sensor types."""
    # Clean up legacy/redundant attributes
    legacy_attrs = [
        "formatted_duration", 
        "timestamp_iso",
        "cell_count", 
        "min_value", "max_value", "mean_value", "median_value"
    ]
    
    for attr in legacy_attrs:
        if attr in attributes:
            del attributes[attr]
    
    # For cell values, standardize naming
    stat_type = attributes.get("stat_type", "cell")
    for key in list(attributes.keys()):
        # Standardize cell value keys
        if any(key.startswith(prefix) for prefix in ["cell_", "voltage_", "temp_", "value_"]):
            if "_" in key and key.split("_")[1].isdigit():
                # Keep only one format (stat_type_N)
                suffix = key.split("_")[1]
                standard_key = f"{stat_type}_{suffix}"
                if key != standard_key:
                    attributes[standard_key] = attributes[key]
                    del attributes[key]
    
    return attributes


class CellVoltageSensor(SensorEntity, RestoreEntity):
    """Representation of a cell voltage sensor."""

    def __init__(
        self,
        unique_id: str,
        name: str,
        topic: str,
        initial_state: Any,
        device_info: DeviceInfo,
        attributes: Dict[str, Any],
        friendly_name: Optional[str] = None,
        hass: Optional[HomeAssistant] = None,
    ):
        """Initialize the sensor."""
        self._attr_unique_id = unique_id
        self._internal_name = name
        self._attr_name = friendly_name or name.replace("_", " ").title()
        self._topic = topic
        self._attr_device_info = device_info or {}
        self._attr_extra_state_attributes = {
            **attributes,
            "topic": topic,
            "last_updated": dt_util.utcnow().isoformat(),
        }
        self.hass = hass

        # Initialize device class and other attributes
        self._attr_device_class = attributes.get("device_class")
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = attributes.get("unit_of_measurement") or attributes.get("unit")
        self._attr_icon = attributes.get("icon")

        # For certain sensors, we need special handling to display formatted values
        if self._attr_device_class in (SensorDeviceClass.DURATION, SensorDeviceClass.TIMESTAMP):
            # Store metadata in attributes but clear from entity properties
            self._attr_extra_state_attributes["original_device_class"] = self._attr_device_class
            self._attr_extra_state_attributes["original_state_class"] = self._attr_state_class
            self._attr_extra_state_attributes["original_unit"] = self._attr_native_unit_of_measurement
            
            # Clear properties so HA doesn't enforce type validation
            self._attr_device_class = None
            self._attr_state_class = None
            self._attr_native_unit_of_measurement = None
        
        # Parse the value
        if requires_numeric_value(self._attr_device_class, self._attr_state_class) and is_special_state_value(initial_state):
            self._parsed_value = None
        else:
            try:
                if isinstance(initial_state, (int, float)) or (isinstance(initial_state, str) and initial_state.replace('.', '', 1).isdigit()):
                    self._parsed_value = float(initial_state)
                else:
                    self._parsed_value = initial_state
            except (ValueError, TypeError):
                self._parsed_value = initial_state

        # Format the value based on original device class for formatted types
        device_class_for_formatting = self._attr_extra_state_attributes.get("original_device_class") or self._attr_device_class
        self._attr_native_value = format_sensor_value(
            self._parsed_value, device_class_for_formatting, self._attr_extra_state_attributes
        )

        # Standardize all attributes
        self._attr_extra_state_attributes = standardize_attributes(self._attr_extra_state_attributes)

        # Set entity_id
        if hass:
            self.entity_id = async_generate_entity_id(
                "sensor.{}", name.lower(),
                hass=hass,
            )

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        await super().async_added_to_hass()

        # Restore previous state if available
        if (state := await self.async_get_last_state()) is not None:
            if state.state not in ["unavailable", "unknown", None]:
                device_class_for_restoring = self._attr_extra_state_attributes.get("original_device_class") or self._attr_device_class
                
                if device_class_for_restoring == SensorDeviceClass.TIMESTAMP:
                    if state.attributes and "raw_value" in state.attributes:
                        self._parsed_value = state.attributes["raw_value"]
                    else:
                        # Try to parse the state if it's a timestamp string
                        self._parsed_value = parse_value(
                            state.state, 
                            device_class_for_restoring,
                            SensorStateClass.MEASUREMENT,
                            False
                        )
                    # Just use the formatted state directly
                    self._attr_native_value = state.state
                elif device_class_for_restoring == SensorDeviceClass.DURATION:
                    # For duration, try to extract raw value from attributes first
                    if state.attributes and "raw_value" in state.attributes:
                        self._parsed_value = state.attributes["raw_value"]
                        # Use the formatted string as the main value
                        self._attr_native_value = format_duration(self._parsed_value)
                    else:
                        # Try to parse the state if it looks like a formatted duration
                        raw_value = parse_duration(state.state)
                        if raw_value is not None:
                            self._parsed_value = raw_value
                            self._attr_native_value = state.state  # Keep the formatted string
                        else:
                            # Just use the state value directly
                            self._attr_native_value = state.state
                else:
                    # For other sensors, use the state directly
                    self._attr_native_value = state.state
                    
            # Restore attributes if available
            if state.attributes:
                # Don't overwrite entity attributes like unit, etc.
                saved_attributes = {
                    k: v for k, v in state.attributes.items()
                    if k not in ["device_class", "state_class", "unit_of_measurement"]
                }
                self._attr_extra_state_attributes.update(saved_attributes)
                
            # Standardize all attributes
            self._attr_extra_state_attributes = standardize_attributes(self._attr_extra_state_attributes)

        @callback
        def update_state(payload: Any) -> None:
            """Update the sensor state."""
            # Parse the value
            if requires_numeric_value(self._attr_device_class, self._attr_state_class) and is_special_state_value(payload):
                self._parsed_value = None
            else:
                try:
                    if isinstance(payload, (int, float)) or (isinstance(payload, str) and payload.replace('.', '', 1).isdigit()):
                        self._parsed_value = float(payload)
                    else:
                        self._parsed_value = payload
                except (ValueError, TypeError):
                    self._parsed_value = payload

            # Format the value using original device class for formatted types
            device_class_for_formatting = self._attr_extra_state_attributes.get("original_device_class") or self._attr_device_class
            self._attr_native_value = format_sensor_value(
                self._parsed_value, device_class_for_formatting, self._attr_extra_state_attributes
            )

            # Standardize all attributes
            self._attr_extra_state_attributes = standardize_attributes(self._attr_extra_state_attributes)

            # Update timestamp
            self._attr_extra_state_attributes["last_updated"] = dt_util.utcnow().isoformat()
            self.async_write_ha_state()

        # Subscribe to updates
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_UPDATE_ENTITY}_{self.unique_id}",
                update_state,
            )
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
        hass: Optional[HomeAssistant] = None,
    ) -> None:
        """Initialize the sensor."""
        self._attr_unique_id = unique_id
        self._internal_name = name
        self._attr_name = friendly_name or name.replace("_", " ").title()
        self._topic = topic
        self._attr_device_info = device_info or {}
        self._attr_extra_state_attributes = {
            **attributes,
            "topic": topic,
            "last_updated": dt_util.utcnow().isoformat(),
        }
        self.hass = hass

        # Set entity_id
        if hass:
            self.entity_id = async_generate_entity_id(
                "sensor.{}", name.lower(), hass=hass,
            )

        # Determine sensor type
        sensor_type = determine_sensor_type(self._internal_name, self._topic, self._attr_extra_state_attributes)
        self._attr_device_class = sensor_type["device_class"]
        self._attr_state_class = sensor_type["state_class"]
        self._attr_native_unit_of_measurement = sensor_type["native_unit_of_measurement"]
        self._attr_entity_category = sensor_type["entity_category"]
        self._attr_icon = sensor_type["icon"]

        # For certain sensors, we need special handling to display formatted values
        if self._attr_device_class in (SensorDeviceClass.DURATION, SensorDeviceClass.TIMESTAMP):
            # Store metadata in attributes but clear from entity properties
            self._attr_extra_state_attributes["original_device_class"] = self._attr_device_class
            self._attr_extra_state_attributes["original_state_class"] = self._attr_state_class
            self._attr_extra_state_attributes["original_unit"] = self._attr_native_unit_of_measurement
            
            # Clear properties so HA doesn't enforce type validation
            self._attr_device_class = None
            self._attr_state_class = None
            self._attr_native_unit_of_measurement = None

        # Add unit to attributes
        if self._attr_native_unit_of_measurement and "unit" not in self._attr_extra_state_attributes:
            self._attr_extra_state_attributes["unit"] = self._attr_native_unit_of_measurement

        # Cell sensor configuration
        self._is_cell_sensor = (
            (("cell" in self._topic.lower() or "voltage" in self._topic.lower() or 
              "temp" in self._topic.lower()) and 
             self._attr_extra_state_attributes.get("category") == "battery") or
            self._attr_extra_state_attributes.get("has_cell_data", False) or
            ("health" in self._topic.lower() and 
             self._attr_extra_state_attributes.get("category") == "tire")
        )
        
        # Store stat type in attributes for standardization
        self._stat_type = "cell"
        if "temp" in self._internal_name.lower():
            self._stat_type = "temp"
        elif "voltage" in self._internal_name.lower():
            self._stat_type = "voltage"
        self._attr_extra_state_attributes["stat_type"] = self._stat_type

        # Initialize cell sensors tracking
        self._cell_sensors_created = False
        self._cell_sensors = []

        # Parse the value using original device class for formatted types
        device_class_for_parsing = self._attr_extra_state_attributes.get("original_device_class") or self._attr_device_class
        state_class_for_parsing = self._attr_extra_state_attributes.get("original_state_class") or self._attr_state_class
        self._parsed_value = parse_value(initial_state, device_class_for_parsing, 
                                       state_class_for_parsing, self._is_cell_sensor)
        
        # Format the value
        self._attr_native_value = format_sensor_value(
            self._parsed_value, device_class_for_parsing, self._attr_extra_state_attributes
        )

        # Extract additional attributes
        if self._is_cell_sensor and isinstance(initial_state, str) and "," in initial_state:
            self._handle_cell_values(initial_state)
        else:
            updated_attrs = process_json_payload(initial_state, self._attr_extra_state_attributes,
                                               self._internal_name, self._is_cell_sensor, self._stat_type)
            self._attr_extra_state_attributes.update(updated_attrs)

        # Add device-specific attributes
        updated_attrs = add_device_specific_attributes(
            self._attr_extra_state_attributes, device_class_for_parsing, self._parsed_value
        )
        self._attr_extra_state_attributes.update(updated_attrs)
        
        # Standardize all attributes
        self._attr_extra_state_attributes = standardize_attributes(self._attr_extra_state_attributes)

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        await super().async_added_to_hass()

        # Restore previous state if available
        if (state := await self.async_get_last_state()) is not None:
            if state.state not in ["unavailable", "unknown", None]:
                device_class_for_restoring = self._attr_extra_state_attributes.get("original_device_class") or self._attr_device_class
                
                if device_class_for_restoring == SensorDeviceClass.TIMESTAMP:
                    if state.attributes and "raw_value" in state.attributes:
                        self._parsed_value = state.attributes["raw_value"]
                    else:
                        # Try to parse the state if it's a timestamp string
                        self._parsed_value = parse_value(
                            state.state, 
                            device_class_for_restoring,
                            self._attr_state_class,
                            self._is_cell_sensor
                        )
                    # Just use the formatted state directly 
                    self._attr_native_value = state.state
                elif device_class_for_restoring == SensorDeviceClass.DURATION:
                    # For duration, try to extract raw value from attributes first
                    if state.attributes and "raw_value" in state.attributes:
                        self._parsed_value = state.attributes["raw_value"]
                        # Use the formatted string as the main value
                        self._attr_native_value = format_duration(self._parsed_value)
                    else:
                        # Try to parse the state if it looks like a formatted duration
                        raw_value = parse_duration(state.state)
                        if raw_value is not None:
                            self._parsed_value = raw_value
                            self._attr_native_value = state.state  # Keep the formatted string
                        else:
                            # Just use the state value directly
                            self._attr_native_value = state.state
                else:
                    # For other sensors, use the state directly
                    self._attr_native_value = state.state
                    
            # Restore attributes if available
            if state.attributes:
                # Don't overwrite entity attributes like unit, etc.
                saved_attributes = {
                    k: v for k, v in state.attributes.items()
                    if k not in ["device_class", "state_class", "unit_of_measurement"]
                }
                self._attr_extra_state_attributes.update(saved_attributes)
            
            # Standardize all attributes
            self._attr_extra_state_attributes = standardize_attributes(self._attr_extra_state_attributes)

        @callback
        def update_state(payload: str) -> None:
            """Update the sensor state."""
            # Parse the value using original values
            device_class_for_parsing = self._attr_extra_state_attributes.get("original_device_class") or self._attr_device_class
            state_class_for_parsing = self._attr_extra_state_attributes.get("original_state_class") or self._attr_state_class
            
            self._parsed_value = parse_value(payload, device_class_for_parsing, 
                                           state_class_for_parsing, self._is_cell_sensor)

            # Format the value
            self._attr_native_value = format_sensor_value(
                self._parsed_value, device_class_for_parsing, self._attr_extra_state_attributes
            )

            # Update timestamp
            self._attr_extra_state_attributes["last_updated"] = dt_util.utcnow().isoformat()

            # Process the payload for attributes
            if self._is_cell_sensor and isinstance(payload, str) and "," in payload:
                self._handle_cell_values(payload)
            else:
                updated_attrs = process_json_payload(payload, self._attr_extra_state_attributes,
                                                  self._internal_name, self._is_cell_sensor, self._stat_type)
                self._attr_extra_state_attributes.update(updated_attrs)

            # Add device-specific attributes
            updated_attrs = add_device_specific_attributes(
                self._attr_extra_state_attributes, device_class_for_parsing, self._parsed_value
            )
            self._attr_extra_state_attributes.update(updated_attrs)
            
            # Standardize all attributes
            self._attr_extra_state_attributes = standardize_attributes(self._attr_extra_state_attributes)

            self.async_write_ha_state()

        # Subscribe to updates
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, f"{SIGNAL_UPDATE_ENTITY}_{self.unique_id}", update_state,
            )
        )

    def _handle_cell_values(self, payload: str) -> None:
        """Handle cell values in payload."""
        try:
            # Parse comma-separated values
            values = [float(part.strip()) for part in payload.split(",") if part.strip()]
            if not values:
                return

            # Store values with consistent naming
            self._attr_extra_state_attributes[f"{self._stat_type}_values"] = values
            self._attr_extra_state_attributes["count"] = len(values)

            # Calculate statistics
            self._attr_extra_state_attributes["median"] = calculate_median(values)
            self._attr_extra_state_attributes["min"] = min(values)
            self._attr_extra_state_attributes["max"] = max(values)

            # Update individual values with standardized naming
            # First clear existing stat_type_N attributes
            for key in list(self._attr_extra_state_attributes.keys()):
                if key.startswith(f"{self._stat_type}_") and key.split("_")[1].isdigit():
                    del self._attr_extra_state_attributes[key]

            # Add new values with standardized naming
            for i, val in enumerate(values):
                self._attr_extra_state_attributes[f"{self._stat_type}_{i+1}"] = val

            # Update cell sensors if created
            if hasattr(self, '_cell_sensors_created') and self._cell_sensors_created and CREATE_INDIVIDUAL_CELL_SENSORS:
                self._update_cell_sensor_values(values)
        except Exception as ex:
            _LOGGER.exception("Error handling cell values: %s", ex)

    def _update_cell_sensor_values(self, cell_values: List[float]) -> None:
        """Update existing cell sensors."""
        if not self.hass or not hasattr(self, '_cell_sensors'):
            return

        for i, value in enumerate(cell_values):
            if i < len(self._cell_sensors):
                cell_id = self._cell_sensors[i]
                async_dispatcher_send(
                    self.hass, f"{SIGNAL_UPDATE_ENTITY}_{cell_id}", value,
                )

    def _create_cell_sensors(self, cell_values: List[float]) -> None:
        """Create individual sensors for each cell value."""
        if self._cell_sensors_created or not self.hass:
            return

        # Extract vehicle_id
        vehicle_id = self.unique_id.split('_')[0]

        # Create sensor configs
        sensor_configs = create_cell_sensors(
            self._topic, cell_values, vehicle_id, self.unique_id, self.device_info,
            {
                "name": self.name,
                "category": self._attr_extra_state_attributes.get("category", "battery"),
                "device_class": self._attr_device_class,
                "unit_of_measurement": self._attr_native_unit_of_measurement,
            },
            CREATE_INDIVIDUAL_CELL_SENSORS
        )

        # Store cell sensor IDs
        self._cell_sensors = [config["unique_id"] for config in sensor_configs]
        self._cell_sensors_created = True

        # Add entities
        if sensor_configs:
            async_dispatcher_send(
                self.hass, SIGNAL_ADD_ENTITIES,
                {
                    "entity_type": "sensor",
                    "cell_sensors": sensor_configs,
                    "parent_entity": self.entity_id,
                }
            )
