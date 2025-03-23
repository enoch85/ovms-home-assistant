"""OVMS sensor entities."""
import logging
import hashlib
import json
from typing import Any, Dict, Optional, List

from homeassistant.components.sensor import SensorEntity, SensorStateClass, SensorDeviceClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from ..const import DOMAIN, LOGGER_NAME, SIGNAL_ADD_ENTITIES, SIGNAL_UPDATE_ENTITY, truncate_state_value
from .parsers import parse_value, process_json_payload, parse_comma_separated_values, requires_numeric_value, is_special_state_value, calculate_median, detect_duration_unit
from .factory import determine_sensor_type, add_device_specific_attributes, create_cell_sensors

_LOGGER = logging.getLogger(LOGGER_NAME)

# Default setting for creating individual cell sensors - matching original behavior
CREATE_INDIVIDUAL_CELL_SENSORS = False

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

        # Use friendly_name when provided
        if friendly_name:
            self._attr_name = friendly_name
        else:
            self._attr_name = name.replace("_", " ").title()

        self._topic = topic
        self._attr_device_info = device_info or {}
        self._attr_extra_state_attributes = {
            **attributes,
            "topic": topic,
            "last_updated": dt_util.utcnow().isoformat(),
        }
        self.hass = hass

        # Initialize device class and other attributes from parent
        self._attr_device_class = attributes.get("device_class")
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = attributes.get("unit_of_measurement")
        self._attr_icon = attributes.get("icon")

        # Only set native value after attributes are initialized
        if requires_numeric_value(self._attr_device_class, self._attr_state_class) and is_special_state_value(initial_state):
            self._attr_native_value = None
        else:
            self._attr_native_value = truncate_state_value(initial_state)

        # Explicitly set entity_id - this ensures consistent naming
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

        @callback
        def update_state(payload: Any) -> None:
            """Update the sensor state."""

            # Parse the value appropriately for the sensor type
            if requires_numeric_value(self._attr_device_class, self._attr_state_class) and is_special_state_value(payload):
                self._attr_native_value = None
            else:
                try:
                    value = float(payload)
                    self._attr_native_value = value
                except (ValueError, TypeError):
                    # Make sure the value is truncated if needed
                    self._attr_native_value = truncate_state_value(payload)

            # Update timestamp attribute
            now = dt_util.utcnow()
            self._attr_extra_state_attributes["last_updated"] = now.isoformat()

            self.async_write_ha_state()

        # Subscribe to updates for this entity
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
        # Use the entity_id compatible name for internal use
        self._internal_name = name

        # Set the entity name that will display in UI - ALWAYS use friendly_name when provided
        if friendly_name:
            self._attr_name = friendly_name
        else:
            self._attr_name = name.replace("_", " ").title()

        self._topic = topic
        self._attr_device_info = device_info or {}
        self._attr_extra_state_attributes = {
            **attributes,
            "topic": topic,
            "last_updated": dt_util.utcnow().isoformat(),
        }
        self.hass = hass

        # Explicitly set entity_id - this ensures consistent naming
        if hass:
            self.entity_id = async_generate_entity_id(
                "sensor.{}",
                name.lower(),
                hass=hass,
            )

        # Try to determine device class and unit
        sensor_type = determine_sensor_type(self._internal_name, self._topic, self._attr_extra_state_attributes)
        self._attr_device_class = sensor_type["device_class"]
        self._attr_state_class = sensor_type["state_class"]
        self._attr_native_unit_of_measurement = sensor_type["native_unit_of_measurement"]
        self._attr_entity_category = sensor_type["entity_category"]
        self._attr_icon = sensor_type["icon"]

        # Flag to indicate if this is a cell sensor
        self._is_cell_sensor = (
            ("cell" in self._topic.lower() or 
             "voltage" in self._topic.lower() or 
             "temp" in self._topic.lower()) and
            self._attr_extra_state_attributes.get("category") == "battery"
        )
        
        # Determine appropriate attribute type name based on the sensor
        self._stat_type = "cell"  # Default fallback
        if "temp" in self._internal_name.lower():
            self._stat_type = "temp"
        elif "voltage" in self._internal_name.lower():
            self._stat_type = "voltage"

        # Special handling for duration sensors
        if self._attr_device_class == SensorDeviceClass.DURATION:
            self._handle_duration_sensor(initial_state)
        else:
            # Only set native value after attributes are initialized - with truncation if needed
            parsed_value = parse_value(initial_state, self._attr_device_class, self._attr_state_class, self._is_cell_sensor)
            self._attr_native_value = truncate_state_value(parsed_value)

        # Try to extract additional attributes from initial state if it's JSON or cell values
        if self._is_cell_sensor and isinstance(initial_state, str) and "," in initial_state:
            # Cell values - process directly with our preferred attribute names
            self._handle_cell_values(initial_state)
        else:
            # Not cell values or already handled - process as JSON
            updated_attrs = process_json_payload(initial_state, self._attr_extra_state_attributes, 
                                               self._internal_name, self._is_cell_sensor, self._stat_type)
            self._attr_extra_state_attributes.update(updated_attrs)

        # Add device-specific attributes
        updated_attrs = add_device_specific_attributes(
            self._attr_extra_state_attributes,
            self._attr_device_class,
            self._attr_native_value
        )
        self._attr_extra_state_attributes.update(updated_attrs)

        # Initialize cell sensors tracking
        self._cell_sensors_created = False
        self._cell_sensors = []

    def _handle_duration_sensor(self, value: Any) -> None:
        """Handle a duration sensor value and process it correctly.
        
        For duration sensors, we store the raw value as an attribute
        and detect the appropriate unit based on the name and topic.
        """
        try:
            # First try to convert to float
            numeric_value = None
            if isinstance(value, (int, float)):
                numeric_value = float(value)
            else:
                try:
                    numeric_value = float(value)
                except (ValueError, TypeError):
                    # Try to parse as JSON
                    try:
                        json_data = json.loads(value)
                        if isinstance(json_data, (int, float)):
                            numeric_value = float(json_data)
                        elif isinstance(json_data, dict) and any(k in json_data for k in ["value", "state"]):
                            # Try to extract value from JSON object
                            for key in ["value", "state"]:
                                if key in json_data and isinstance(json_data[key], (int, float)):
                                    numeric_value = float(json_data[key])
                                    break
                    except (ValueError, json.JSONDecodeError):
                        pass

            if numeric_value is not None:
                # Store raw value in attributes
                self._attr_extra_state_attributes["raw_value"] = numeric_value
                
                # Detect appropriate time unit
                unit = detect_duration_unit(self._topic, self._internal_name, numeric_value)
                self._attr_extra_state_attributes["unit"] = unit
                
                # Store value in seconds
                self._attr_native_value = numeric_value
            else:
                # If conversion fails, still store the original value
                self._attr_native_value = None
                if value is not None:
                    self._attr_extra_state_attributes["original_value"] = value
        except Exception as ex:
            _LOGGER.exception("Error handling duration sensor: %s", ex)
            self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        await super().async_added_to_hass()

        # Restore previous state if available
        if (state := await self.async_get_last_state()) is not None:
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

        @callback
        def update_state(payload: str) -> None:
            """Update the sensor state."""
            # Special handling for duration sensors
            if self._attr_device_class == SensorDeviceClass.DURATION:
                self._handle_duration_sensor(payload)
            else:
                # Parse value and apply truncation if needed
                parsed_value = parse_value(payload, self._attr_device_class, self._attr_state_class, self._is_cell_sensor)
                self._attr_native_value = truncate_state_value(parsed_value)

            # Update timestamp attribute
            now = dt_util.utcnow()
            self._attr_extra_state_attributes["last_updated"] = now.isoformat()

            # Process the payload based on its type
            if self._is_cell_sensor and isinstance(payload, str) and "," in payload:
                # Cell values - process directly with our preferred attribute names
                self._handle_cell_values(payload)
            else:
                # Not cell values or already handled - process as JSON
                updated_attrs = process_json_payload(payload, self._attr_extra_state_attributes, 
                                                 self._internal_name, self._is_cell_sensor, self._stat_type)
                self._attr_extra_state_attributes.update(updated_attrs)

            # Add device-specific attributes
            updated_attrs = add_device_specific_attributes(
                self._attr_extra_state_attributes,
                self._attr_device_class,
                self._attr_native_value
            )
            self._attr_extra_state_attributes.update(updated_attrs)

            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_UPDATE_ENTITY}_{self.unique_id}",
                update_state,
            )
        )
