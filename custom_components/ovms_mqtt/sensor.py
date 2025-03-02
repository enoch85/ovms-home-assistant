"""Sensor platform for OVMS MQTT integration."""
import logging

from homeassistant.components.mqtt import subscription
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ovms_mqtt"

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the OVMS MQTT sensor platform."""
    _LOGGER.info("Setting up OVMS MQTT sensor platform")

    async def message_received(msg):
        """Handle new MQTT messages."""
        _LOGGER.debug(f"Received message: {msg.topic} {msg.payload}")

        # Extract vehicle ID and metric key from the topic
        parts = msg.topic.split("/")
        if len(parts) >= 3:
            vehicle_id = parts[1]
            metric_key = "/".join(parts[3:])
            sensor_id = f"ovms_{vehicle_id}_{metric_key.replace('/', '_')}"

            # Create or update the sensor
            async_add_entities([OVMSMQTTSensor(sensor_id, msg.topic, msg.payload)])

    # Subscribe to all OVMS topics
    await subscription.async_subscribe_topics(hass, {
        "ovms_notify_topic": {
            "topic": "ovms/+/notify/#",
            "msg_callback": message_received
        },
        "ovms_metrics_topic": {
            "topic": "ovms/+/metrics/#",
            "msg_callback": message_received
        }
    })

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

    @callback
    def async_update(self):
        """Update the sensor state."""
        self._state = self._payload
