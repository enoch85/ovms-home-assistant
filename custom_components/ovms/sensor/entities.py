"""OVMS sensor entities."""
import logging
import hashlib
import json
from typing import Any, Dict, Optional, List

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from ..const import DOMAIN, LOGGER_NAME, SIGNAL_ADD_ENTITIES, SIGNAL_UPDATE_ENTITY, truncate_state_value
from .parsers import parse_value, process_json_payload, parse_comma_separated_values, requires_numeric_value, is_special_state_value, calculate_median
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

    def _handle_cell_values(self, payload: str) -> None:
        """Handle cell values in payload.
        
        Adds cell data as attributes to this sensor.
        Uses descriptive attribute names (voltage/temp) rather than generic "cell".
        """
        try:
            # Parse comma-separated values
            values = [float(part.strip()) for part in payload.split(",") if part.strip()]
            if not values:
                return
                
            # Add the cell values to the attributes - use only one attribute name for the array 
            # based on the type of sensor (remove legacy/duplicate array names)
            self._attr_extra_state_attributes[f"{self._stat_type}_values"] = values
            self._attr_extra_state_attributes["count"] = len(values)
            
            # REMOVE legacy/duplicate names to avoid duplication
            if "cell_values" in self._attr_extra_state_attributes and self._stat_type != "cell":
                del self._attr_extra_state_attributes["cell_values"]
            if "values" in self._attr_extra_state_attributes:
                del self._attr_extra_state_attributes["values"]
            if "cell_count" in self._attr_extra_state_attributes:
                del self._attr_extra_state_attributes["cell_count"]

            # Calculate and store statistics
            median_value = calculate_median(values)
            avg_value = sum(values) / len(values)
            min_value = min(values)
            max_value = max(values)

            # Store statistics as attributes
            self._attr_extra_state_attributes["median"] = median_value
            self._attr_extra_state_attributes["min"] = min_value
            self._attr_extra_state_attributes["max"] = max_value
            
            # REMOVE duplicate stats attributes to avoid duplication
            for legacy_key in ["min_value", "max_value", "mean_value", "median_value"]:
                if legacy_key in self._attr_extra_state_attributes:
                    del self._attr_extra_state_attributes[legacy_key]

            # Store individual values with descriptive names only
            # First clear any existing cell_N attributes to prevent duplicates
            for key in list(self._attr_extra_state_attributes.keys()):
                # Remove both old "cell_N" and potentially existing "voltage_N" attributes 
                # to ensure no duplication of previous attributes
                if (key.startswith("cell_") or key.startswith("voltage_") or 
                    key.startswith("temp_") or key.startswith("value_")):
                    if key.split("_")[1].isdigit():
                        del self._attr_extra_state_attributes[key]
            
            # Now add with the proper type
            for i, val in enumerate(values):
                self._attr_extra_state_attributes[f"{self._stat_type}_{i+1}"] = val

            # Update existing cell sensors if they exist and are enabled
            if hasattr(self, '_cell_sensors_created') and self._cell_sensors_created and CREATE_INDIVIDUAL_CELL_SENSORS:
                self._update_cell_sensor_values(values)
        except Exception as ex:
            _LOGGER.exception("Error handling cell values: %s", ex)

    def _update_cell_sensor_values(self, cell_values: List[float]) -> None:
        """Update the values of existing cell sensors."""
        if not self.hass or not hasattr(self, '_cell_sensors'):
            return

        # Update each cell sensor with its new value
        for i, value in enumerate(cell_values):
            if i < len(self._cell_sensors):
                cell_id = self._cell_sensors[i]
                # Use the dispatcher to signal an update
                async_dispatcher_send(
                    self.hass,
                    f"{SIGNAL_UPDATE_ENTITY}_{cell_id}",
                    value,
                )

    def _create_cell_sensors(self, cell_values: List[float]) -> None:
        """Create individual sensors for each cell value."""
        # Skip creating individual sensors if the flag is set
        if hasattr(self, '_cell_sensors_created') and self._cell_sensors_created:
            return

        # Skip if no hass instance
        if not self.hass:
            return
            
        # Extract vehicle_id from unique_id
        vehicle_id = self.unique_id.split('_')[0]
        
        # Create cell sensor configurations using factory function
        sensor_configs = create_cell_sensors(
            self._topic,
            cell_values,
            vehicle_id,
            self.unique_id,
            self.device_info,
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
        
        # Flag cells as created
        self._cell_sensors_created = True
        
        # Create and add entities through the entity discovery mechanism if we have configs
        if sensor_configs:
            async_dispatcher_send(
                self.hass,
                SIGNAL_ADD_ENTITIES,
                {
                    "entity_type": "sensor",
                    "cell_sensors": sensor_configs,
                    "parent_entity": self.entity_id,
                }
            )
