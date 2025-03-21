"""OVMS sensor entities."""
import logging
from typing import Any, Dict, Optional, List

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from ..const import DOMAIN, LOGGER_NAME, SIGNAL_ADD_ENTITIES, SIGNAL_UPDATE_ENTITY, truncate_state_value
from .parsers import parse_value, process_json_payload, parse_comma_separated_values, requires_numeric_value, is_special_state_value
from .factory import determine_sensor_type, add_device_specific_attributes, create_cell_sensors

_LOGGER = logging.getLogger(LOGGER_NAME)

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
        config: Optional[Dict[str, Any]] = None
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
        self.config = config or {}

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

        # Only set native value after attributes are initialized - with truncation if needed
        parsed_value = parse_value(initial_state, self._attr_device_class, self._attr_state_class)
        self._attr_native_value = truncate_state_value(parsed_value)

        # Try to extract additional attributes from initial state if it's JSON
        updated_attrs = process_json_payload(initial_state, self._attr_extra_state_attributes)
        self._attr_extra_state_attributes.update(updated_attrs)

        # Add device-specific attributes
        updated_attrs = add_device_specific_attributes(
            self._attr_extra_state_attributes,
            self._attr_device_class,
            self._attr_native_value
        )
        self._attr_extra_state_attributes.update(updated_attrs)

        # Check for cell values in initial payload
        if isinstance(initial_state, str) and "," in initial_state:
            self._handle_cell_values_as_attributes(initial_state)

        # Initialize cell sensors tracking - default to not creating separate cell sensors
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
                
                # Restore the cell_sensors_created flag if present
                if "_cell_sensors_created" in saved_attributes:
                    self._cell_sensors_created = saved_attributes["_cell_sensors_created"]

        @callback
        def update_state(payload: str) -> None:
            """Update the sensor state."""
            # Parse value and apply truncation if needed
            parsed_value = parse_value(payload, self._attr_device_class, self._attr_state_class)
            self._attr_native_value = truncate_state_value(parsed_value)

            # Update timestamp attribute
            now = dt_util.utcnow()
            self._attr_extra_state_attributes["last_updated"] = now.isoformat()

            # Try to extract additional attributes from payload if it's JSON
            updated_attrs = process_json_payload(payload, self._attr_extra_state_attributes)
            self._attr_extra_state_attributes.update(updated_attrs)

            # Handle cell values in payload - prioritize attribute creation
            if isinstance(payload, str) and "," in payload:
                self._handle_cell_values_as_attributes(payload)

                # Only create separate cell sensors if explicitly configured
                if self.config.get("create_cell_sensors", False) and not self._cell_sensors_created:
                    self._handle_cell_values_as_sensors(payload)

            # Add device-specific attributes
            updated_attrs = add_device_specific_attributes(
                self._attr_extra_state_attributes,
                self._attr_device_class,
                self._attr_native_value
            )
            self._attr_extra_state_attributes.update(updated_attrs)
            
            # Store cell sensors creation flag in attributes for persistence
            self._attr_extra_state_attributes["_cell_sensors_created"] = self._cell_sensors_created

            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_UPDATE_ENTITY}_{self.unique_id}",
                update_state,
            )
        )

    def _handle_cell_values_as_attributes(self, payload: str) -> None:
        """Handle cell values in payload by creating attributes."""
        try:
            # Try to parse as comma-separated values
            result = parse_comma_separated_values(payload)
            if result and "cell_values" in result:
                cell_values = result["cell_values"]
                # Update all statistical attributes
                for key, value in result.items():
                    if key != "value":  # Skip the main value as we just want attributes
                        self._attr_extra_state_attributes[key] = value
                
                # Add individual cell values as attributes
                for i, val in enumerate(cell_values):
                    self._attr_extra_state_attributes[f"cell_{i+1}"] = val
        except Exception as ex:
            _LOGGER.exception("Error handling cell values as attributes: %s", ex)

    def _handle_cell_values_as_sensors(self, payload: str) -> None:
        """Create individual sensors for each cell value if configured to do so."""
        # Skip if not configured to create separate cell sensors
        if not self.config.get("create_cell_sensors", False):
            return
            
        # Skip creating individual sensors if already created
        if self._cell_sensors_created:
            return

        # Skip if no hass instance
        if not self.hass:
            return
            
        try:
            # Try to parse as comma-separated values
            result = parse_comma_separated_values(payload)
            if result and "cell_values" in result:
                cell_values = result["cell_values"]
                
                # Extract vehicle_id from unique_id
                vehicle_id = self.unique_id.split('_')[0]
                
                # Create cell sensor configurations
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
                    }
                )
                
                # Store cell sensor IDs
                self._cell_sensors = [config["unique_id"] for config in sensor_configs]
                
                # Flag cells as created
                self._cell_sensors_created = True
                
                # Create and add entities through the entity discovery mechanism
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
        except Exception as ex:
            _LOGGER.exception("Error handling cell values as sensors: %s", ex)

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
