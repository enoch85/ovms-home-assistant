"""Support for OVMS sensors."""
import logging
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..const import LOGGER_NAME, SIGNAL_ADD_ENTITIES
from .entities import OVMSSensor, CellVoltageSensor

_LOGGER = logging.getLogger(LOGGER_NAME)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up OVMS sensors based on a config entry."""
    # Get config data with defaults
    config = entry.data.copy()
    config.update(entry.options)
    # Default to not creating individual cell sensors
    create_cell_sensors = config.get("create_cell_sensors", False)
    
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
                # Only add cell sensors if explicitly configured
                if create_cell_sensors:
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
                else:
                    _LOGGER.debug("Skipping cell sensor creation as per configuration")
            except Exception as ex:
                _LOGGER.error("Error creating cell sensors: %s", ex)
            return

        try:
            sensor = OVMSSensor(
                unique_id=data.get("unique_id", ""),
                name=data.get("name", "unknown"),
                topic=data.get("topic", ""),
                initial_state=data.get("payload", ""),
                device_info=data.get("device_info", {}),
                attributes=data.get("attributes", {}),
                friendly_name=data.get("friendly_name"),
                hass=hass,
                config=config
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
