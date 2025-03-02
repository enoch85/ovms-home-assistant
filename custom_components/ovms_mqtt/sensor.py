"""Sensor platform for OVMS MQTT integration."""
import logging

from homeassistant.components.mqtt import async_subscribe
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the OVMS MQTT sensor platform."""
    config = config_entry.data
    topic_prefix = config.get("topic_prefix", "ovms")

    @callback
    def message_received(msg):
        """Handle new MQTT messages."""
        _LOGGER.debug("Received message: %s %s", msg.topic, msg.payload)

        # Extract vehicle ID and metric key from the topic
        parts = msg.topic.split("/")
        if len(parts) >= 3:
            vehicle_id = parts[1]
            metric_key = "/".join(parts[3:])
            sensor_id = f"ovms_{vehicle_id}_{metric_key.replace('/', '_')}"

            # Create or update the sensor
            async_add_entities([
                OVMSMQTTSensor(sensor_id, msg.topic, msg.payload)
            ])

    # Subscribe to all OVMS topics
    _LOGGER.debug("Subscribing to MQTT topics with prefix: %s", topic_prefix)
    await async_subscribe(
        hass,
        f"{topic_prefix}/+/notify/#",
        message_received,
    )
    await async_subscribe(
        hass,
        f"{topic_prefix}/+/metrics/#",
        message_received,
    )
    _LOGGER.debug("Successfully subscribed to MQTT topics")


class OVMSMQTTSensor(SensorEntity):
    """Representation of an OVMS MQTT sensor."""

    def __init__(self, sensor_id, topic, payload):
        """Initialize the sensor."""
        self._sensor_id = sensor_id
        self._topic = topic
        self._payload = payload
        self._state = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"OVMS {self._sensor_id}"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unique_id(self):
        """Return a unique ID for the sensor."""
        return self._sensor_id

    @callback
    def async_update(self):
        """Update the sensor state."""
        self._state = self._payload
