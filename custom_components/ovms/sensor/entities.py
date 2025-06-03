"""OVMS sensor entities."""
import logging
from typing import Any, Dict, Optional, List
from datetime import datetime

from homeassistant.components.sensor import SensorEntity, SensorStateClass, SensorDeviceClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util
from ..const import LOGGER_NAME, SIGNAL_ADD_ENTITIES, SIGNAL_UPDATE_ENTITY, truncate_state_value
from .parsers import parse_value, process_json_payload, requires_numeric_value, is_special_state_value, calculate_median
from .factory import determine_sensor_type, add_device_specific_attributes, create_cell_sensors
from .duration_formatter import format_duration, parse_duration
from ..metrics.common.tire import TIRE_POSITIONS

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
    if device_class == SensorDeviceClass.TIMESTAMP:
        # For timestamp, store datetime object as attribute and return ISO string
        attributes["timestamp_object"] = value
        if isinstance(value, datetime):
            formatted = value.isoformat()
            # Make it more readable by just keeping date and time
            if 'T' in formatted:
                date_part, time_part = formatted.split('T')
                time_part = time_part.split('+')[0].split('.')[0]  # Remove milliseconds and timezone
                return f"{date_part} at {time_part}"
            return formatted
        return str(value)
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
        self.hass: Optional[HomeAssistant] = hass

        # Initialize device class and other attributes
        self._attr_device_class = attributes.get("device_class")
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = attributes.get("unit_of_measurement") or attributes.get("unit")
        self._attr_icon = attributes.get("icon")

        # For timestamp sensors, set explicit metadata values
        if self._attr_device_class == SensorDeviceClass.TIMESTAMP:
            self._attr_state_class = None
            self._attr_native_unit_of_measurement = None

        # For certain sensors, we need special handling to display formatted values
        if self._attr_device_class in (SensorDeviceClass.DURATION, SensorDeviceClass.TIMESTAMP):
            # Store metadata in attributes but clear from entity properties
            self._attr_extra_state_attributes["original_device_class"] = self._attr_device_class

            if self._attr_device_class == SensorDeviceClass.TIMESTAMP:
                self._attr_extra_state_attributes["original_state_class"] = "timestamp"
                self._attr_extra_state_attributes["original_unit"] = "timestamp"
            else:
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
                    if state.attributes and "timestamp_object" in state.attributes:
                        self._parsed_value = state.attributes["timestamp_object"]
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
                        device_class_for_formatting = self._attr_extra_state_attributes.get("original_device_class") or self._attr_device_class
                        self._attr_native_value = format_sensor_value(
                            self._parsed_value, device_class_for_formatting, self._attr_extra_state_attributes
                        )
                    else:
                        # Try to parse the state if it looks like a formatted duration
                        raw_value = parse_duration(state.state)
                        if raw_value is not None:
                            self._parsed_value = raw_value
                            self._attr_native_value = state.state  # Keep the formatted string
                            self._attr_extra_state_attributes["raw_value"] = raw_value
                            self._attr_extra_state_attributes["formatted_short"] = state.state

                            # Remove any debug or legacy attributes
                            for field in ["formatted_duration", "determined_unit", "unit_uncertain",
                                         "unit_defaulted", "debug_unit_used"]:
                                if field in self._attr_extra_state_attributes:
                                    del self._attr_extra_state_attributes[field]
                        else:
                            # Just use the state value directly
                            self._attr_native_value = state.state
                else:
                    # For other sensors, use the state directly
                    self._attr_native_value = state.state

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
        if self.hass:
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
        self.hass: Optional[HomeAssistant] = hass

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
            self._attr_state_class = None
            self._attr_native_unit_of_measurement = None

        # For certain sensors, we need special handling to display formatted values
        if self._attr_device_class in (SensorDeviceClass.DURATION, SensorDeviceClass.TIMESTAMP):
            # Store metadata in attributes but clear from entity properties
            self._attr_extra_state_attributes["original_device_class"] = self._attr_device_class

            if self._attr_device_class == SensorDeviceClass.TIMESTAMP:
                self._attr_extra_state_attributes["original_state_class"] = "timestamp"
                self._attr_extra_state_attributes["original_unit"] = "timestamp"
            else:
                self._attr_extra_state_attributes["original_state_class"] = self._attr_state_class
                self._attr_extra_state_attributes["original_unit"] = self._attr_native_unit_of_measurement

            # Clear properties so HA doesn't enforce type validation
            self._attr_device_class = None
            self._attr_state_class = None
            self._attr_native_unit_of_measurement = None

        # Add unit to attributes
        if self._attr_native_unit_of_measurement and "unit" not in self._attr_extra_state_attributes:
            self._attr_extra_state_attributes["unit"] = self._attr_native_unit_of_measurement

        # Cell sensor configuration - detect by topic patterns and known cell data metrics
        self._is_cell_sensor = (
            (("cell" in self._topic.lower() or "voltage" in self._topic.lower() or
              "temp" in self._topic.lower()) and
             self._attr_extra_state_attributes.get("category") == "battery") or
            self._attr_extra_state_attributes.get("has_cell_data", False) or
            self._attr_extra_state_attributes.get("category") == "tire"  # All tire metrics have multiple values
        )

        # Determine stat type based on category and topic content
        self._stat_type = "cell"  # Default fallback
        
        # Check if this is a tire sensor by category
        if self._attr_extra_state_attributes.get("category") == "tire":
            # For tire sensors, determine the metric type
            if "pressure" in self._topic.lower() or "emgcy" in self._topic.lower() or "diff" in self._topic.lower():
                self._stat_type = "pressure"
            elif "temp" in self._topic.lower():
                self._stat_type = "temp"
            elif "health" in self._topic.lower():
                self._stat_type = "health"
            elif "alert" in self._topic.lower():
                self._stat_type = "alert"
            else:
                self._stat_type = "tire"  # fallback for unknown tire metrics
        elif "temp" in self._internal_name.lower():
            self._stat_type = "temp"
        elif "voltage" in self._internal_name.lower():
            self._stat_type = "voltage"

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

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        await super().async_added_to_hass()

        # Restore previous state if available
        if (state := await self.async_get_last_state()) is not None:
            if state.state not in ["unavailable", "unknown", None]:
                device_class_for_restoring = self._attr_extra_state_attributes.get("original_device_class") or self._attr_device_class

                if device_class_for_restoring == SensorDeviceClass.TIMESTAMP:
                    if state.attributes and "timestamp_object" in state.attributes:
                        self._parsed_value = state.attributes["timestamp_object"]
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
                            self._attr_native_value = state.state  # Keep the formatted string
                            self._attr_extra_state_attributes["formatted_short"] = state.state

                            # Remove any debug or legacy attributes
                            for field in ["formatted_duration", "determined_unit", "unit_uncertain",
                                         "unit_defaulted", "debug_unit_used"]:
                                if field in self._attr_extra_state_attributes:
                                    del self._attr_extra_state_attributes[field]
                        else:
                            # Just use the state value directly
                            self._attr_native_value = state.state
                else:
                    # For other sensors, use the state directly
                    self._attr_native_value = state.state

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

            self.async_write_ha_state()

        # Subscribe to updates
        if self.hass:
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

            # Remove legacy names
            for old_key in ["cell_values", "values", "cell_count"]:
                if old_key in self._attr_extra_state_attributes and (old_key != "cell_values" or self._stat_type != "cell"):
                    del self._attr_extra_state_attributes[old_key]

            # Calculate statistics
            self._attr_extra_state_attributes["median"] = calculate_median(values)
            self._attr_extra_state_attributes["min"] = min(values)
            self._attr_extra_state_attributes["max"] = max(values)

            # Remove legacy stats
            for legacy_key in ["min_value", "max_value", "mean_value", "median_value"]:
                if legacy_key in self._attr_extra_state_attributes:
                    del self._attr_extra_state_attributes[legacy_key]

            # Update individual values
            # First clear existing attributes
            for key in list(self._attr_extra_state_attributes.keys()):
                if any(key.startswith(prefix) for prefix in ["cell_", "voltage_", "temp_", "value_", "pressure_", "health_", "alert_"]):
                    # Clear both numeric and tire position keys
                    key_parts = key.split("_")
                    if len(key_parts) >= 2 and (key_parts[1].isdigit() or key_parts[1].lower() in ["fl", "fr", "lr", "rr"]):
                        del self._attr_extra_state_attributes[key]

            # Add new values with appropriate naming
            for i, val in enumerate(values):
                if self._attr_extra_state_attributes.get("category") == "tire" and i < 4:
                    # Use tire position codes for any tire sensor
                    position_name, position_code = TIRE_POSITIONS[i]
                    self._attr_extra_state_attributes[f"{self._stat_type}_{position_code}"] = val
                else:
                    # Use numeric naming for other sensors
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
        vehicle_id = (self.unique_id or "unknown").split('_')[0]

        # Create sensor configs
        device_info_dict: Dict[str, Any] = {}
        if self.device_info:
            if isinstance(self.device_info, dict):
                device_info_dict = self.device_info  # type: ignore
            else:
                # Extract relevant fields from DeviceInfo
                try:
                    device_info_dict = {
                        "identifiers": getattr(self.device_info, 'identifiers', set()),
                        "name": getattr(self.device_info, 'name', ""),
                        "manufacturer": getattr(self.device_info, 'manufacturer', ""),
                        "model": getattr(self.device_info, 'model', ""),
                    }
                except Exception:
                    device_info_dict = {}
        sensor_configs = create_cell_sensors(
            self._topic, cell_values, vehicle_id, self.unique_id or "unknown", device_info_dict,
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
