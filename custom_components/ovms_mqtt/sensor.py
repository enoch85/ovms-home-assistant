import logging
import json
from homeassistant.components.mqtt import client as mqtt_client
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers import entity_platform

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the OVMS MQTT sensor platform."""
    _LOGGER.debug("Starting async_setup_entry for OVMS MQTT sensor platform")

    config = config_entry.data
    topic_prefix = config.get("topic_prefix", "ovms")
    platform = entity_platform.async_get_current_platform()

    coordinator = MQTTCoordinator(hass, config, async_add_entities, topic_prefix)
    await coordinator.async_setup()

    return True

class MQTTCoordinator:
    """Coordinate MQTT messages and entity creation."""

    def __init__(self, hass, config, async_add_entities, topic_prefix):
        self.hass = hass
        self.config = config
        self.async_add_entities = async_add_entities
        self.topic_prefix = topic_prefix
        self._added_entities = set()

    async def async_setup(self):
        """Subscribe to MQTT topics."""
        _LOGGER.debug("Subscribing to MQTT topics with prefix: %s", self.topic_prefix)

        topics = [
            f"{self.topic_prefix}/+/+/metric/#",
            f"{self.topic_prefix}/+/+/notify/#"
        ]

        for topic in topics:
            _LOGGER.debug("Subscribing to topic: %s", topic)
            await mqtt_client.async_subscribe(
                self.hass,
                topic,
                self.message_received,
                self.config.get("qos", 1),
                encoding="utf-8"
            )

    @callback
    def message_received(self, msg):
        """Handle incoming MQTT messages."""
        try:
            _LOGGER.debug("Received message on topic: %s, payload: %s", msg.topic, msg.payload)

            # Example topic: ovms/{vehicle_id}/{sensor_type}/metric/{metric_name}
            parts = msg.topic.split("/")
            if len(parts) < 5:
                _LOGGER.warning("Invalid topic structure: %s", msg.topic)
                return

            vehicle_id = parts[1]
            sensor_type = parts[2]  # metric/notify
            metric = parts[4]

            unique_id = f"ovms_{vehicle_id}_{sensor_type}_{metric}"
            name = f"OVMS {vehicle_id} {metric.replace('_', ' ').title()}"

            # Create or update the sensor entity
            sensor = MQTTSensor(
                self.config,
                msg.topic,
                vehicle_id,
                sensor_type,
                metric,
                unique_id,
                name
            )

            # Update the sensor state
            sensor.update_state(msg.payload)

            # Add entity to Home Assistant
            self.hass.async_create_task(
                self._async_add_entity(sensor)
            )

        except Exception as e:
            _LOGGER.error("Error processing message: %s", str(e))

    async def _async_add_entity(self, sensor):
        """Add entity if it doesn't exist."""
        if sensor.unique_id not in self._added_entities:
            _LOGGER.debug("Adding new entity: %s", sensor.unique_id)
            self._added_entities.add(sensor.unique_id)
            await self.async_add_entities([sensor], update_before_add=True)

class MQTTSensor(SensorEntity):
    """Representation of an OVMS MQTT sensor."""

    def __init__(self, config, topic, vehicle_id, sensor_type, metric, unique_id, name):
        self._config = config
        self._topic = topic
        self._vehicle_id = vehicle_id
        self._sensor_type = sensor_type
        self._metric = metric
        self._attr_unique_id = unique_id
        self._attr_name = name
        self._attr_native_value = None
        self._attr_available = True  # Assume available unless told otherwise

    def update_state(self, payload):
        """Update the sensor state from the MQTT payload."""
        try:
            self._attr_native_value = float(payload)
        except ValueError:
            self._attr_native_value = payload

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {("ovms", self._vehicle_id)},
            "name": f"OVMS Vehicle {self._vehicle_id}",
            "manufacturer": "Open Vehicles"
        }
