import logging
import json
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.mqtt import async_subscribe  # Import async_subscribe directly
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import Entity
from .const import DOMAIN, CONF_BROKER, CONF_PORT, CONF_USERNAME, CONF_PASSWORD, CONF_TOPIC_PREFIX, CONF_QOS

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> bool:
    """Set up OVMS MQTT sensor platform from a config entry."""
    _LOGGER.debug("Starting async_setup_entry for OVMS MQTT sensor platform")

    config = entry.data
    broker = config[CONF_BROKER]
    port = config[CONF_PORT]
    username = config[CONF_USERNAME]
    password = config[CONF_PASSWORD]
    topic_prefix = config.get(CONF_TOPIC_PREFIX, "ovms")
    qos = config.get(CONF_QOS, 1)

    _LOGGER.debug(
        f"Configuration loaded: broker={broker}, port={port}, username={username}, "
        f"topic_prefix={topic_prefix}, qos={qos}"
    )

    # Store the configuration in hass.data
    hass.data[DOMAIN] = {
        'entities': {},
        'config': config
    }
    _LOGGER.debug("Configuration stored in hass.data")

    # Subscribe to MQTT topics
    await subscribe_to_topics(hass, topic_prefix, async_add_entities)
    _LOGGER.debug("MQTT topics subscribed successfully")
    return True


async def subscribe_to_topics(
    hass: HomeAssistant,
    topic_prefix: str,
    async_add_entities: AddEntitiesCallback
):
    """Subscribe to relevant MQTT topics."""
    _LOGGER.debug(f"Subscribing to MQTT topics with prefix: {topic_prefix}")

    # Subscribe to metric topics
    await async_subscribe(
        hass,
        f"{topic_prefix}/+/+/metric/#",
        lambda msg: handle_metric_update(hass, msg, async_add_entities)
    )
    _LOGGER.debug(f"Subscribed to topic: {topic_prefix}/+/+/metric/#")

    # Subscribe to notification topics
    await async_subscribe(
        hass,
        f"{topic_prefix}/+/+/notify/#",
        lambda msg: handle_notification_update(hass, msg)
    )
    _LOGGER.debug(f"Subscribed to topic: {topic_prefix}/+/+/notify/#")


def handle_metric_update(
    hass: HomeAssistant,
    msg,
    async_add_entities: AddEntitiesCallback
):
    """Handle incoming MQTT messages for metrics."""
    _LOGGER.debug(f"Received MQTT message: topic={msg.topic}, payload={msg.payload}")

    topic = msg.topic
    payload = msg.payload
    config = hass.data[DOMAIN]['config']
    topic_prefix = config.get(CONF_TOPIC_PREFIX, "ovms")

    _LOGGER.debug(f"Parsing topic: {topic}")
    parts = topic.split('/')
    if len(parts) >= 5 and parts[0] == topic_prefix and parts[3] == 'metric':
        vehicle_name = parts[1]  # Dynamic vehicle name
        vin = parts[2]  # Dynamic VIN
        metric_key = '/'.join(parts[4:])  # Full metric key

        _LOGGER.debug(f"Parsed metric: vehicle_name={vehicle_name}, vin={vin}, metric_key={metric_key}")

        # Parse the payload (assuming JSON or plain text)
        try:
            value = json.loads(payload)
            _LOGGER.debug(f"Payload parsed as JSON: {value}")
        except json.JSONDecodeError:
            value = payload
            _LOGGER.debug(f"Payload is plain text: {value}")

        # Create or update the sensor entity
        update_sensor_entity(hass, vin, metric_key, value, async_add_entities)
    else:
        _LOGGER.warning(f"Topic does not match expected structure: {topic}")


def handle_notification_update(hass: HomeAssistant, msg):
    """Handle incoming MQTT messages for notifications."""
    _LOGGER.debug(f"Received MQTT message: topic={msg.topic}, payload={msg.payload}")

    topic = msg.topic
    payload = msg.payload
    config = hass.data[DOMAIN]['config']
    topic_prefix = config.get(CONF_TOPIC_PREFIX, "ovms")

    _LOGGER.debug(f"Parsing topic: {topic}")
    parts = topic.split('/')
    if len(parts) >= 5 and parts[0] == topic_prefix and parts[3] == 'notify':
        vehicle_name = parts[1]  # Dynamic vehicle name
        vin = parts[2]  # Dynamic VIN
        notification_type = '/'.join(parts[4:])  # Full notification type

        _LOGGER.debug(
            f"Parsed notification: vehicle_name={vehicle_name}, vin={vin}, "
            f"notification_type={notification_type}"
        )

        # Log the notification (or trigger an automation)
        _LOGGER.info(f"Notification received for {vin}: {notification_type} = {payload}")
    else:
        _LOGGER.warning(f"Topic does not match expected structure: {topic}")


def update_sensor_entity(
    hass: HomeAssistant,
    vin: str,
    metric_key: str,
    value,
    async_add_entities: AddEntitiesCallback
):
    """Create or update a sensor entity."""
    entity_id = f"sensor.{vin}_{metric_key.replace('/', '_')}"
    entities = hass.data[DOMAIN]['entities']

    _LOGGER.debug(f"Updating sensor entity: entity_id={entity_id}, value={value}")

    if entity_id not in entities:
        # Create a new sensor entity
        _LOGGER.debug(f"Creating new sensor entity: {entity_id}")
        sensor = OvmsSensor(vin, metric_key, value)
        entities[entity_id] = sensor
        async_add_entities([sensor])
    else:
        # Update the existing entity
        _LOGGER.debug(f"Updating existing sensor entity: {entity_id}")
        entities[entity_id].update_value(value)


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
