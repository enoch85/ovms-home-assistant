from homeassistant.helpers.entity import Entity
from homeassistant.const import STATE_UNKNOWN

class OvmsSensor(Entity):
    """Representation of an OVMS MQTT sensor."""

    def __init__(self, vin: str, metric_key: str, value):
        """Initialize the sensor."""
        self._vin = vin
        self._metric_key = metric_key
        self._value = value
        self._unique_id = f"{vin}_{metric_key.replace('/', '_')}"
        self._name = f"OVMS {vin} {metric_key.replace('/', ' ')}"

    @property
    def unique_id(self):
        """Return a unique ID for the sensor."""
        return self._unique_id

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._value

    @property
    def should_poll(self):
        """No polling needed for MQTT sensors."""
        return False

    def update_value(self, value):
        """Update the sensor's value."""
        self._value = value
        self.schedule_update_ha_state()
