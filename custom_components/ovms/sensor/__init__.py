"""Support for OVMS sensors."""
import logging
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import SensorDeviceClass

from ..const import LOGGER_NAME, SIGNAL_ADD_ENTITIES
from .entities import OVMSSensor, CellVoltageSensor, OVMSDurationSensor

_LOGGER = logging.getLogger(LOGGER_NAME)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up OVMS sensors based on a config entry."""
    @callback
    def async_add_sensor(data: Dict[str, Any]) -> None:
        """Add sensor based on discovery data."""
        if not data or not isinstance(data, dict):
            _LOGGER.warning("Invalid entity data received: %s", data)
            return

        # Skip if it's not a sensor
        if data.get("entity_type") != "sensor":
            return

        _LOGGER.info("Adding sensor: %s", data.get("name", "unknown"))

        # Handle cell sensors differently
        if "cell_sensors" in data:
            _LOGGER.debug("Adding cell sensors from parent entity: %s", data.get("parent_entity"))
            try:
                sensors = []
                for cell_config in data["cell_sensors"]:
                    sensor = CellVoltageSensor(
                        cell_config["unique_id"],
                        cell_config["name"],
                        cell_config.get("topic", ""),
                        cell_config.get("state"),
                        cell_config.get("device_info", {}),
                        cell_config.get("attributes", {}),
                        cell_config.get("friendly_name"),
                        hass,
                    )
                    sensors.append(sensor)

                async_add_entities(sensors)
            except Exception as ex:
                _LOGGER.error("Error creating cell sensors: %s", ex)
            return

        try:
            # Check if the sensor has DURATION device class defined in the metrics
            device_class = None
            topic = data.get("topic", "")
            if "attributes" in data and isinstance(data["attributes"], dict):
                device_class = data["attributes"].get("device_class")
                
            # If we have a GPS time sensor, ensure it uses timestamp class
            if "gpstime" in topic:
                _LOGGER.debug("Detected GPS time sensor from topic %s, ensuring timestamp class", topic)
                device_class = SensorDeviceClass.TIMESTAMP
                # Update the data too to ensure consistency
                if "attributes" in data and isinstance(data["attributes"], dict):
                    data["attributes"]["device_class"] = SensorDeviceClass.TIMESTAMP
            
            _LOGGER.debug("Sensor %s has device class %s from metrics", data.get("name"), device_class)
            is_duration = device_class == SensorDeviceClass.DURATION
                
            if is_duration:
                # Create a formatted duration sensor
                _LOGGER.debug("Creating duration sensor %s", data.get("name"))
                sensor = OVMSDurationSensor(
                    data.get("unique_id", ""),
                    data.get("name", "unknown"),
                    data.get("topic", ""),
                    data.get("payload", ""),
                    data.get("device_info", {}),
                    data.get("attributes", {}),
                    data.get("friendly_name"),
                    hass,
                )
            else:
                # Create a regular sensor
                _LOGGER.debug("Creating standard sensor %s with device class %s", 
                             data.get("name"), device_class)
                sensor = OVMSSensor(
                    data.get("unique_id", ""),
                    data.get("name", "unknown"),
                    data.get("topic", ""),
                    data.get("payload", ""),
                    data.get("device_info", {}),
                    data.get("attributes", {}),
                    data.get("friendly_name"),
                    hass,
                )

            async_add_entities([sensor])
        except Exception as ex:
            _LOGGER.error("Error creating sensor: %s", ex)

    # Subscribe to discovery events
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_ADD_ENTITIES, async_add_sensor)
    )

    # Signal that all platforms are loaded
    async_dispatcher_send(hass, "ovms_sensor_platform_loaded")
