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
    qos = config.get("qos", 1)

    @callback
    def message_received(msg):
        """Handle new MQTT messages."""
        _LOGGER.debug("Received message: %s %s", msg.topic, msg.payload)

        # Extract user, vehicle_id, and topic type (metric/notify/client) from the topic
        parts = msg.topic.split("/")
        if len(parts) >= 4:  # ovms/user/vehicle_id/[metric|notify|client]/...
            user = parts[1]
            vehicle_id = parts[2]
            topic_type = parts[3]  # metric, notify, or client
            metric_path = "/".join(parts[4:])  # Everything after the topic type

            # Create a unique sensor ID and name
            sensor_id = f"ovms_{user}_{vehicle_id}_{topic_type}_{metric_path.replace('/', '_')}"
            sensor_name = f"OVMS {vehicle_id} {topic_type} {metric_path.replace('/', ' ')}"

            # Create or update the sensor
            async_add_entities([
                OVMSMQTTSensor(sensor_id, sensor_name, msg.topic, msg.payload)
            ])

    # Subscribe to all relevant topics using wildcards
    topics = [
        f"{topic_prefix}/+/+/metric/#",
        f"{topic_prefix}/+/+/notify/#",
        f"{topic_prefix}/+/+/client/#",
    ]

    for topic in topics:
        _LOGGER.debug("Subscribing to MQTT topic: %s with QoS: %s", topic, qos)
        await async_subscribe(
            hass,
            topic,
            message_received,
            qos=qos,
        )
    _LOGGER.debug("Successfully subscribed to MQTT topics")


class OVMSMQTTSensor(SensorEntity):
    """Representation of an OVMS MQTT sensor."""

    def __init__(self, sensor_id, name, topic, payload):
        """Initialize the sensor."""
        self._sensor_id = sensor_id
        self._name = name
        self._topic = topic
        self._payload = payload
        self._state = None

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

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
