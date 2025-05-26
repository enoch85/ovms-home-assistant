"""OVMS sensor entities."""
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
from homeassistant.const import UnitOfTime

from ..const import DOMAIN, LOGGER_NAME, SIGNAL_ADD_ENTITIES, SIGNAL_UPDATE_ENTITY, truncate_state_value
from .parsers import parse_value, process_json_payload, requires_numeric_value, is_special_state_value, calculate_median # Removed unused 'parse_timestamp'
from .factory import determine_sensor_type, add_device_specific_attributes, create_cell_sensors, create_tire_pressure_sensors
from .duration_formatter import format_duration, parse_duration

_LOGGER = logging.getLogger(LOGGER_NAME)

# Default setting for creating individual cell sensors
CREATE_INDIVIDUAL_CELL_SENSORS = False

def format_sensor_value(value, device_class, attributes):
    """Format sensor value based on device class, returns formatted value."""
    if value is None:
        return None

    if device_class == SensorDeviceClass.DURATION:
        # For duration, store raw value as attribute
        attributes["raw_value"] = value

        # Get the original unit directly from the metric definition in attributes
        original_unit = attributes.get("original_unit")

        # First format with short format (for main display)
        formatted_short = format_duration(value, original_unit, False)

        # Also format with full names for the attribute
        formatted_full = format_duration(value, original_unit, True)

        # Store both values in attributes
        attributes["formatted_value"] = formatted_full
        attributes["formatted_short"] = formatted_short

        # Remove any legacy or debug fields
        for field in ["determined_unit", "unit_uncertain", "unit_defaulted", "debug_unit_used", "use_full_names"]:
            if field in attributes:
                del attributes[field]

        # Return the short format as the main value
        return formatted_short
    elif device_class == SensorDeviceClass.TIMESTAMP:
        if not isinstance(value, datetime):
            # This should ideally not happen if parse_value is correct
            _LOGGER.warning(f"Timestamp sensor received non-datetime value: {value} (type: {type(value)}). Attempting to re-parse.")
            # Attempt to re-parse, assuming it might be a raw string/number from MQTT not yet processed
            # Pass None for state_class as it's not directly relevant for timestamp parsing itself here
            parsed_dt = parse_value(value, SensorDeviceClass.TIMESTAMP, None) 
            if not isinstance(parsed_dt, datetime):
                _LOGGER.error(f"Failed to re-parse timestamp value: {value}. Sensor state might be incorrect.")
                return str(value) # Fallback to string representation
            value = parsed_dt

        # Ensure the datetime object is UTC. If naive, assume UTC.
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            value_utc = value.replace(tzinfo=dt_util.UTC)
        else:
            value_utc = value.astimezone(dt_util.UTC)

        attributes["timestamp_object"] = value_utc # Store the UTC datetime object
        
        # Format for display: YYYY-MM-DD at HH:MM:SS (in local time if HA is configured, else UTC)
        # Home Assistant handles localization of timestamps for display automatically
        # when a proper datetime object is set as the state.
        # The native_value should be the datetime object itself.
        return value_utc # Return the datetime object directly for HA to handle
    else:
        # Normal handling
        return truncate_state_value(value)


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

        # For timestamp sensors, set explicit metadata values
        if self._attr_device_class == SensorDeviceClass.TIMESTAMP:
            self._attr_state_class = None # Timestamps don't have a state class like 'measurement'
            self._attr_native_unit_of_measurement = None # Timestamps don't have a unit of measurement
            # HA will automatically format the datetime object for display
        # For certain sensors, we need special handling to display formatted values
        # This block is primarily for DURATION. TIMESTAMP is now handled by returning datetime object.
        if self._attr_device_class == SensorDeviceClass.DURATION: # Removed TIMESTAMP from this condition
            # Store metadata in attributes but clear from entity properties
            self._attr_extra_state_attributes["original_device_class"] = self._attr_device_class
            self._attr_extra_state_attributes["original_state_class"] = self._attr_state_class
            self._attr_extra_state_attributes["original_unit"] = self._attr_native_unit_of_measurement

            # Clear properties so HA doesn't enforce type validation for DURATION string display
            self._attr_device_class = None
            self._attr_state_class = None
            self._attr_native_unit_of_measurement = None

        # Add unit to attributes if not already set by metric definition's attributes
        if self._attr_native_unit_of_measurement and "unit" not in self._attr_extra_state_attributes:
            self._attr_extra_state_attributes["unit"] = self._attr_native_unit_of_measurement

        # Cell sensor configuration
        self._is_cell_sensor = (
            (("cell" in self._topic.lower() or "voltage" in self._topic.lower() or
              "temp" in self._topic.lower()) and
             self._attr_extra_state_attributes.get("category") == "battery") or
            self._attr_extra_state_attributes.get("has_cell_data", False) or
            (("health" in self._topic.lower() or "pressure" in self._topic.lower()) and # Added pressure here for robust check
             self._attr_extra_state_attributes.get("category") == "tire")
        )
        
        # Determine stat type
        self._stat_type = "cell" # Default
        if self._attr_extra_state_attributes.get("category") == "tire" and self._attr_device_class == SensorDeviceClass.PRESSURE:
            self._stat_type = "pressure"
        elif "temp" in self._internal_name.lower():
            self._stat_type = "temp"
        elif "voltage" in self._internal_name.lower():
            self._stat_type = "voltage"


        # Initialize cell sensors tracking
        self._cell_sensors_created = False
        self._cell_sensors = []
        
        # Initialize tire pressure sensors tracking
        self._tire_sensors_created = False
        self._tire_sensors = []

        device_class_for_parsing = self._attr_extra_state_attributes.get("original_device_class") or self._attr_device_class
        state_class_for_parsing = self._attr_extra_state_attributes.get("original_state_class") or self._attr_state_class
        
        parsed_data_or_value = parse_value(
            initial_state, 
            device_class_for_parsing,
            state_class_for_parsing, 
            self._is_cell_sensor, # This flag might need re-evaluation for pressure sensors if it causes issues
            entity_name=self._internal_name
        )

        attributes_processed_from_dict = False
        if isinstance(parsed_data_or_value, dict) and device_class_for_parsing == SensorDeviceClass.PRESSURE:
            self._parsed_value = parsed_data_or_value.get("value")
            detected_unit = parsed_data_or_value.get("detected_unit")
            if detected_unit:
                self._attr_native_unit_of_measurement = detected_unit
                self._attr_extra_state_attributes["unit"] = detected_unit
            
            for key, val in parsed_data_or_value.items():
                if key not in ["value", "detected_unit"]:
                    self._attr_extra_state_attributes[key] = val
            attributes_processed_from_dict = True
        else:
            self._parsed_value = parsed_data_or_value

        self._attr_native_value = format_sensor_value(
            self._parsed_value, device_class_for_parsing, self._attr_extra_state_attributes
        )

        if not attributes_processed_from_dict:
            # Check if this is a cell sensor (non-pressure) with comma-separated values
            is_non_pressure_comma_separated_cell_sensor = (
                self._is_cell_sensor and 
                isinstance(initial_state, str) and 
                ("," in initial_state or ";" in initial_state) and 
                device_class_for_parsing != SensorDeviceClass.PRESSURE
            )
            if is_non_pressure_comma_separated_cell_sensor:
                 self._handle_cell_values(initial_state) # Handles its own attribute extraction
            else:
                # For other cases (including if initial_state is JSON, or simple string not handled above)
                updated_attrs = process_json_payload(initial_state, self._attr_extra_state_attributes,
                                                   self._internal_name, self._is_cell_sensor, self._stat_type)
                self._attr_extra_state_attributes.update(updated_attrs)
        
        updated_attrs_device_specific = add_device_specific_attributes(
            self._attr_extra_state_attributes, device_class_for_parsing, self._parsed_value
        )
        self._attr_extra_state_attributes.update(updated_attrs_device_specific)

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        await super().async_added_to_hass()

        # Restore previous state if available
        if (state := await self.async_get_last_state()) is not None:
            if state.state not in ["unavailable", "unknown", None]:
                device_class_for_restoring = self._attr_extra_state_attributes.get("original_device_class") or self._attr_device_class
                # Ensure state_class_for_restoring is defined at this scope
                current_state_class = self._attr_state_class # Default to current entity state_class
                if self._attr_extra_state_attributes.get("original_state_class"):
                    current_state_class = self._attr_extra_state_attributes.get("original_state_class")
                state_class_for_restoring = current_state_class

                if self._attr_device_class == SensorDeviceClass.TIMESTAMP:
                    # The state.state from HA for a timestamp is typically an ISO string
                    # parse_value will convert this to a datetime object
                    parsed_val = parse_value(state.state, SensorDeviceClass.TIMESTAMP, None)
                    if isinstance(parsed_val, datetime):
                        self._parsed_value = parsed_val
                        self._attr_native_value = parsed_val
                        if "timestamp_object" in state.attributes:
                            restored_ts_obj = parse_value(state.attributes["timestamp_object"], SensorDeviceClass.TIMESTAMP, None)
                            if isinstance(restored_ts_obj, datetime):
                                self._attr_extra_state_attributes["timestamp_object"] = restored_ts_obj
                            else:
                                self._attr_extra_state_attributes["timestamp_object"] = parsed_val
                        else:
                            self._attr_extra_state_attributes["timestamp_object"] = parsed_val
                    else:
                        _LOGGER.warning(f"Could not restore timestamp for {self.entity_id} from state '{state.state}'. Parsed as: {parsed_val}")
                        self._attr_native_value = state.state # Fallback
                elif device_class_for_restoring == SensorDeviceClass.DURATION:
                    # For duration, try to extract raw value from attributes first
                    if state.attributes and "raw_value" in state.attributes:
                        self._parsed_value = state.attributes["raw_value"]
                        device_class_for_formatting = self._attr_extra_state_attributes.get("original_device_class") or self._attr_device_class
                        self._attr_native_value = format_sensor_value(
                            self._parsed_value, device_class_for_formatting, self._attr_extra_state_attributes
                        )
                    else:
                        # Try to parse the state if it looks like a formatted duration
                        raw_value = parse_duration(state.state)
                        if raw_value is not None:
                            self._parsed_value = raw_value
                            self._attr_extra_state_attributes["raw_value"] = raw_value
                            self._attr_native_value = state.state
                            self._attr_extra_state_attributes["formatted_short"] = state.state
                            for field in ["formatted_duration", "determined_unit", "unit_uncertain",
                                         "unit_defaulted", "debug_unit_used"]:
                                if field in self._attr_extra_state_attributes:
                                    del self._attr_extra_state_attributes[field]
                        else:
                            self._attr_native_value = state.state
                else:
                    # For other sensors, parse the state value appropriately
                    # Now state_class_for_restoring is correctly defined and used here
                    self._parsed_value = parse_value(state.state, device_class_for_restoring, state_class_for_restoring, self._is_cell_sensor, entity_name=self._internal_name)
                    self._attr_native_value = format_sensor_value(self._parsed_value, device_class_for_restoring, self._attr_extra_state_attributes)

            # Restore attributes if available, but clean up inconsistent ones
            if state.attributes:
                # Don't overwrite entity attributes like unit, etc.
                saved_attributes = {
                    k: v for k, v in state.attributes.items()
                    if k not in ["device_class", "state_class", "unit_of_measurement"]
                }

                # Remove stale/inconsistent formatted attributes
                if "formatted_duration" in saved_attributes:
                    del saved_attributes["formatted_duration"]

                self._attr_extra_state_attributes.update(saved_attributes)

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
        self._internal_name = name  # Used for logging and entity_name in parsers
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

        # For timestamp sensors, set explicit metadata values
        if self._attr_device_class == SensorDeviceClass.TIMESTAMP:
            self._attr_state_class = None # Timestamps don't have a state class like 'measurement'
            self._attr_native_unit_of_measurement = None # Timestamps don't have a unit of measurement
            # HA will automatically format the datetime object for display
        # For certain sensors, we need special handling to display formatted values
        # This block is primarily for DURATION. TIMESTAMP is now handled by returning datetime object.
        if self._attr_device_class == SensorDeviceClass.DURATION: # Removed TIMESTAMP from this condition
            # Store metadata in attributes but clear from entity properties
            self._attr_extra_state_attributes["original_device_class"] = self._attr_device_class
            self._attr_extra_state_attributes["original_state_class"] = self._attr_state_class
            self._attr_extra_state_attributes["original_unit"] = self._attr_native_unit_of_measurement

            # Clear properties so HA doesn't enforce type validation for DURATION string display
            self._attr_device_class = None
            self._attr_state_class = None
            self._attr_native_unit_of_measurement = None

        # Add unit to attributes if not already set by metric definition's attributes
        if self._attr_native_unit_of_measurement and "unit" not in self._attr_extra_state_attributes:
            self._attr_extra_state_attributes["unit"] = self._attr_native_unit_of_measurement

        # Cell sensor configuration
        self._is_cell_sensor = (
            (("cell" in self._topic.lower() or "voltage" in self._topic.lower() or
              "temp" in self._topic.lower()) and
             self._attr_extra_state_attributes.get("category") == "battery") or
            self._attr_extra_state_attributes.get("has_cell_data", False) or
            (("health" in self._topic.lower() or "pressure" in self._topic.lower()) and # Added pressure here for robust check
             self._attr_extra_state_attributes.get("category") == "tire")
        )
        
        # Determine stat type
        self._stat_type = "cell" # Default
        if self._attr_extra_state_attributes.get("category") == "tire" and self._attr_device_class == SensorDeviceClass.PRESSURE:
            self._stat_type = "pressure"
        elif "temp" in self._internal_name.lower():
            self._stat_type = "temp"
        elif "voltage" in self._internal_name.lower():
            self._stat_type = "voltage"


        # Initialize cell sensors tracking
        self._cell_sensors_created = False
        self._cell_sensors = []
        
        # Initialize tire pressure sensors tracking
        self._tire_sensors_created = False
        self._tire_sensors = []

        device_class_for_parsing = self._attr_extra_state_attributes.get("original_device_class") or self._attr_device_class
        state_class_for_parsing = self._attr_extra_state_attributes.get("original_state_class") or self._attr_state_class
        
        parsed_data_or_value = parse_value(
            initial_state, 
            device_class_for_parsing,
            state_class_for_parsing, 
            self._is_cell_sensor, # This flag might need re-evaluation for pressure sensors if it causes issues
            entity_name=self._internal_name
        )

        attributes_processed_from_dict = False
        if isinstance(parsed_data_or_value, dict) and device_class_for_parsing == SensorDeviceClass.PRESSURE:
            self._parsed_value = parsed_data_or_value.get("value")
            detected_unit = parsed_data_or_value.get("detected_unit")
            if detected_unit:
                self._attr_native_unit_of_measurement = detected_unit
                self._attr_extra_state_attributes["unit"] = detected_unit
            
            for key, val in parsed_data_or_value.items():
                if key not in ["value", "detected_unit"]:
                    self._attr_extra_state_attributes[key] = val
            attributes_processed_from_dict = True
        else:
            self._parsed_value = parsed_data_or_value

        self._attr_native_value = format_sensor_value(
            self._parsed_value, device_class_for_parsing, self._attr_extra_state_attributes
        )

        if not attributes_processed_from_dict:
            # Check if this is a cell sensor (non-pressure) with comma-separated values
            is_non_pressure_comma_separated_cell_sensor = (
                self._is_cell_sensor and 
                isinstance(initial_state, str) and 
                ("," in initial_state or ";" in initial_state) and 
                device_class_for_parsing != SensorDeviceClass.PRESSURE
            )
            if is_non_pressure_comma_separated_cell_sensor:
                 self._handle_cell_values(initial_state) # Handles its own attribute extraction
            else:
                # For other cases (including if initial_state is JSON, or simple string not handled above)
                updated_attrs = process_json_payload(initial_state, self._attr_extra_state_attributes,
                                                   self._internal_name, self._is_cell_sensor, self._stat_type)
                self._attr_extra_state_attributes.update(updated_attrs)
        
        updated_attrs_device_specific = add_device_specific_attributes(
            self._attr_extra_state_attributes, device_class_for_parsing, self._parsed_value
        )
        self._attr_extra_state_attributes.update(updated_attrs_device_specific)

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        await super().async_added_to_hass()

        # Restore previous state if available
        if (state := await self.async_get_last_state()) is not None:
            if state.state not in ["unavailable", "unknown", None]:
                device_class_for_restoring = self._attr_extra_state_attributes.get("original_device_class") or self._attr_device_class
                # Ensure state_class_for_restoring is defined at this scope
                current_state_class = self._attr_state_class # Default to current entity state_class
                if self._attr_extra_state_attributes.get("original_state_class"):
                    current_state_class = self._attr_extra_state_attributes.get("original_state_class")
                state_class_for_restoring = current_state_class

                if self._attr_device_class == SensorDeviceClass.TIMESTAMP:
                    # The state.state from HA for a timestamp is typically an ISO string
                    # parse_value will convert this to a datetime object
                    parsed_val = parse_value(state.state, SensorDeviceClass.TIMESTAMP, None)
                    if isinstance(parsed_val, datetime):
                        self._parsed_value = parsed_val
                        self._attr_native_value = parsed_val
                        if "timestamp_object" in state.attributes:
                            restored_ts_obj = parse_value(state.attributes["timestamp_object"], SensorDeviceClass.TIMESTAMP, None)
                            if isinstance(restored_ts_obj, datetime):
                                self._attr_extra_state_attributes["timestamp_object"] = restored_ts_obj
                            else:
                                self._attr_extra_state_attributes["timestamp_object"] = parsed_val
                        else:
                            self._attr_extra_state_attributes["timestamp_object"] = parsed_val
                    else:
                        _LOGGER.warning(f"Could not restore timestamp for {self.entity_id} from state '{state.state}'. Parsed as: {parsed_val}")
                        self._attr_native_value = state.state # Fallback
                elif device_class_for_restoring == SensorDeviceClass.DURATION:
                    # For duration, try to extract raw value from attributes first
                    if state.attributes and "raw_value" in state.attributes:
                        self._parsed_value = state.attributes["raw_value"]
                        device_class_for_formatting = self._attr_extra_state_attributes.get("original_device_class") or self._attr_device_class
                        self._attr_native_value = format_sensor_value(
                            self._parsed_value, device_class_for_formatting, self._attr_extra_state_attributes
                        )
                    else:
                        # Try to parse the state if it looks like a formatted duration
                        raw_value = parse_duration(state.state)
                        if raw_value is not None:
                            self._parsed_value = raw_value
                            self._attr_extra_state_attributes["raw_value"] = raw_value
                            self._attr_native_value = state.state
                            self._attr_extra_state_attributes["formatted_short"] = state.state
                            for field in ["formatted_duration", "determined_unit", "unit_uncertain",
                                         "unit_defaulted", "debug_unit_used"]:
                                if field in self._attr_extra_state_attributes:
                                    del self._attr_extra_state_attributes[field]
                        else:
                            self._attr_native_value = state.state
                else:
                    # For other sensors, parse the state value appropriately
                    # Now state_class_for_restoring is correctly defined and used here
                    self._parsed_value = parse_value(state.state, device_class_for_restoring, state_class_for_restoring, self._is_cell_sensor, entity_name=self._internal_name)
                    self._attr_native_value = format_sensor_value(self._parsed_value, device_class_for_restoring, self._attr_extra_state_attributes)

            # Restore attributes if available, but clean up inconsistent ones
            if state.attributes:
                # Don't overwrite entity attributes like unit, etc.
                saved_attributes = {
                    k: v for k, v in state.attributes.items()
                    if k not in ["device_class", "state_class", "unit_of_measurement"]
                }

                # Remove stale/inconsistent formatted attributes
                if "formatted_duration" in saved_attributes:
                    del saved_attributes["formatted_duration"]

                self._attr_extra_state_attributes.update(saved_attributes)

        @callback
        def update_state(payload: str) -> None:
            """Update the sensor state."""
            # Determine the correct device_class for parsing and formatting
            # If original_device_class exists (duration/timestamp special handling), use that.
            # Otherwise, use the entity's current device_class.
            device_class_for_processing = self._attr_extra_state_attributes.get("original_device_class") or self._attr_device_class
            state_class_for_processing = self._attr_extra_state_attributes.get("original_state_class") or self._attr_state_class

            # If this entity is a timestamp sensor, its _attr_device_class is SensorDeviceClass.TIMESTAMP
            if self._attr_device_class == SensorDeviceClass.TIMESTAMP:
                parsed_val = parse_value(payload, SensorDeviceClass.TIMESTAMP, None) # state_class not needed for timestamp parsing
                if isinstance(parsed_val, datetime):
                    self._parsed_value = parsed_val
                    self._attr_native_value = parsed_val # Set native_value to the datetime object
                    self._attr_extra_state_attributes["timestamp_object"] = parsed_val
                else:
                    _LOGGER.warning(f"Failed to parse timestamp payload '{payload}' for {self.entity_id}. Current state: {self._attr_native_value}")
                    # Optionally, decide if you want to set to None or keep old value
                    # For now, let's not change native_value if parsing fails, to avoid flapping to unavailable
                    # self._attr_native_value = None 
                    # self._parsed_value = None
            else:
                # Existing logic for non-timestamp sensors
                parsed_result = parse_value(
                    payload, 
                    device_class_for_processing, # Use determined device_class for parsing
                    state_class_for_processing, 
                    self._is_cell_sensor, 
                    entity_name=self._internal_name
                )

                attributes_processed_from_dict = False
                if isinstance(parsed_result, dict) and device_class_for_processing == SensorDeviceClass.PRESSURE:
                    self._parsed_value = parsed_result.get("value")
                    detected_unit = parsed_result.get("detected_unit")
                    if detected_unit:
                        self._attr_native_unit_of_measurement = detected_unit
                        self._attr_extra_state_attributes["unit"] = detected_unit
                    
                    for key, val in parsed_result.items():
                        if key not in ["value", "detected_unit"]:
                            self._attr_extra_state_attributes[key] = val
                    attributes_processed_from_dict = True
                else:
                    self._parsed_value = parsed_result

                # Format the value based on its actual device_class (not original_device_class for formatting here, except for DURATION)
                # For DURATION, format_sensor_value uses original_device_class from attributes
                self._attr_native_value = format_sensor_value(
                    self._parsed_value, device_class_for_processing, self._attr_extra_state_attributes
                )

                if not attributes_processed_from_dict:
                    is_non_pressure_comma_separated_cell_sensor = (
                        self._is_cell_sensor and 
                        isinstance(payload, str) and 
                        ("," in payload or ";" in payload) and 
                        device_class_for_processing != SensorDeviceClass.PRESSURE
                    )
                    if is_non_pressure_comma_separated_cell_sensor:
                        self._handle_cell_values(payload)
                    else:
                        updated_attrs = process_json_payload(payload, self._attr_extra_state_attributes,
                                                          self._internal_name, self._is_cell_sensor, self._stat_type)
                        self._attr_extra_state_attributes.update(updated_attrs)
                
                updated_attrs_device_specific = add_device_specific_attributes(
                    self._attr_extra_state_attributes, device_class_for_processing, self._parsed_value
                )
                self._attr_extra_state_attributes.update(updated_attrs_device_specific)

            self._attr_extra_state_attributes["last_updated"] = dt_util.utcnow().isoformat()
            self.async_write_ha_state()

    def _handle_cell_values(self, payload: str) -> None:
        """Handle cell values in payload."""
        try:
            separator = ";" if ";" in payload else ","
            values = [float(val.strip()) for val in payload.split(separator) if val.strip()]

            if not values:
                return

            # Check if this is a tire pressure sensor with 4 values
            if (self._stat_type == "pressure" and 
                self._attr_extra_state_attributes.get("category") == "tire" and 
                len(values) == 4):
                self._handle_tire_pressure_values(values)
            else:
                # Handle regular cell values (battery cells, etc.)
                self._handle_regular_cell_values(values)
                
        except Exception as ex:
            _LOGGER.exception("Error handling cell values: %s", ex)
    
    def _handle_tire_pressure_values(self, pressure_values: List[float]) -> None:
        """Handle tire pressure values specifically."""
        try:
            # Store tire pressure statistics
            self._attr_extra_state_attributes["count"] = len(pressure_values)
            self._attr_extra_state_attributes["min"] = min(pressure_values)
            self._attr_extra_state_attributes["max"] = max(pressure_values)
            self._attr_extra_state_attributes["mean"] = round(sum(pressure_values) / len(pressure_values), 4)
            self._attr_extra_state_attributes["median"] = calculate_median(pressure_values)

            # Store individual tire pressure values with descriptive names
            tire_positions = ["front_left", "front_right", "rear_left", "rear_right"]
            for i, (position, value) in enumerate(zip(tire_positions, pressure_values)):
                self._attr_extra_state_attributes[f"tire_{position}"] = value
                self._attr_extra_state_attributes[f"pressure_{i+1}"] = value  # Keep numeric indexing too

            # Create individual tire sensors if enabled
            if CREATE_INDIVIDUAL_CELL_SENSORS:  # Reuse the same configuration flag
                self._create_tire_pressure_sensors(pressure_values)

            # Update tire sensor values if they exist
            if hasattr(self, '_tire_sensors_created') and self._tire_sensors_created:
                self._update_tire_sensor_values(pressure_values)
                
        except Exception as ex:
            _LOGGER.exception("Error handling tire pressure values: %s", ex)
    
    def _handle_regular_cell_values(self, values: List[float]) -> None:
        """Handle regular cell values (battery cells, etc.)."""
        try:
            # Store cell statistics
            self._attr_extra_state_attributes["count"] = len(values)
            self._attr_extra_state_attributes["min"] = min(values)
            self._attr_extra_state_attributes["max"] = max(values)
            self._attr_extra_state_attributes["mean"] = round(sum(values) / len(values), 4)
            self._attr_extra_state_attributes["median"] = calculate_median(values)

            # Remove legacy stats
            for legacy_key in ["min_value", "max_value", "mean_value", "median_value"]:
                if legacy_key in self._attr_extra_state_attributes:
                    del self._attr_extra_state_attributes[legacy_key]

            # Update individual values
            # First clear existing attributes
            for key in list(self._attr_extra_state_attributes.keys()):
                if any(key.startswith(prefix) for prefix in ["cell_", "voltage_", "temp_", "value_"]):
                    if key.split("_")[1].isdigit():
                        del self._attr_extra_state_attributes[key]

            # Add new values
            for i, val in enumerate(values):
                self._attr_extra_state_attributes[f"{self._stat_type}_{i+1}"] = val

            # Create individual cell sensors if enabled
            if CREATE_INDIVIDUAL_CELL_SENSORS:
                self._create_cell_sensors(values)

            # Update cell sensors if created
            if hasattr(self, '_cell_sensors_created') and self._cell_sensors_created and CREATE_INDIVIDUAL_CELL_SENSORS:
                self._update_cell_sensor_values(values)
                
        except Exception as ex:
            _LOGGER.exception("Error handling regular cell values: %s", ex)

    def _create_tire_pressure_sensors(self, pressure_values: List[float]) -> None:
        """Create individual sensors for each tire pressure value."""
        if self._tire_sensors_created or not self.hass or len(pressure_values) != 4:
            return

        # Extract vehicle_id
        vehicle_id = self.unique_id.split('_')[0]

        # Create sensor configs
        sensor_configs = create_tire_pressure_sensors(
            self._topic, pressure_values, vehicle_id, self.unique_id, self.device_info,
            {
                "name": self.name,
                "category": self._attr_extra_state_attributes.get("category", "tire"),
                "device_class": self._attr_device_class,
                "unit_of_measurement": self._attr_native_unit_of_measurement,
            },
            CREATE_INDIVIDUAL_CELL_SENSORS  # Reuse the same configuration flag
        )

        # Store tire sensor IDs
        self._tire_sensors = [config["unique_id"] for config in sensor_configs]
        self._tire_sensors_created = True

        # Add entities
        if sensor_configs:
            async_dispatcher_send(
                self.hass, SIGNAL_ADD_ENTITIES,
                {
                    "entity_type": "sensor",
                    "tire_sensors": sensor_configs,
                    "parent_entity": self.entity_id,
                }
            )

    def _update_tire_sensor_values(self, pressure_values: List[float]) -> None:
        """Update existing tire pressure sensors."""
        if not self.hass or not hasattr(self, '_tire_sensors'):
            return

        for i, value in enumerate(pressure_values):
            if i < len(self._tire_sensors):
                tire_id = self._tire_sensors[i]
                async_dispatcher_send(
                    self.hass, f"{SIGNAL_UPDATE_ENTITY}_{tire_id}", value,
                )
