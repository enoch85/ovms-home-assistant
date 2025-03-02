import logging
from homeassistant.helpers.entity import Entity
from homeassistant.const import STATE_UNKNOWN

_LOGGER = logging.getLogger(__name__)

class OvmsSensor(Entity):
    """Representation of an OVMS MQTT sensor."""

    def __init__(self, vin: str, metric_key: str, value):
        """Initialize the sensor."""
        _LOGGER.debug(f"Initializing OvmsSensor: vin={vin}, metric_key={metric_key}, value={value}")
        self._vin = vin
        self._metric_key = metric_key
        self._value = value
        self._unique_id = f"{vin}_{metric_key.replace('/', '_')}"
        self._name = f"OVMS {vin} {metric_key.replace('/', ' ')}"
        _LOGGER.debug(f"Created sensor with unique_id={self._unique_id}, name={self._name}")

    @property
    def unique_id(self):
        """Return a unique ID for the sensor."""
        _LOGGER.debug(f"Getting unique_id: {self._unique_id}")
        return self._unique_id

    @property
    def name(self):
        """Return the name of the sensor."""
        _LOGGER.debug(f"Getting name: {self._name}")
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        _LOGGER.debug(f"Getting state: {self._value}")
        return self._value

    @property
    def should_poll(self):
        """No polling needed for MQTT sensors."""
        _LOGGER.debug("Polling is disabled for this sensor")
        return False

    def update_value(self, value):
        """Update the sensor's value."""
        _LOGGER.debug(f"Updating sensor value: {self._value} -> {value}")
        self._value = value
        self.schedule_update_ha_state()
        _LOGGER.debug("Sensor value updated and state scheduled for update")
