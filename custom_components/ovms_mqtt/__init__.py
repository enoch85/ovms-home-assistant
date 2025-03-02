import logging
import json
from homeassistant.core import HomeAssistant
from homeassistant.components.mqtt import subscription
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .sensor import OvmsSensor

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ovms_mqtt"

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the OVMS MQTT integration."""
    hass.data[DOMAIN] = {'entities': {}}

    # Subscribe to MQTT topics
    await subscribe_to_topics(hass)
    return True

async def subscribe_to_topics(hass: HomeAssistant):
    """Subscribe to relevant MQTT topics."""
    await hass.components.mqtt.async_subscribe(
        "ovms/+/+/metric/#",
        lambda msg: handle_metric_update(hass, msg)
    )
    await hass.components.mqtt.async_subscribe(
        "ovms/+/+/notify/#",
        lambda msg: handle_notification_update(hass, msg)
    )

def handle_metric_update(hass: HomeAssistant, msg):
    """Handle incoming MQTT messages for metrics."""
    topic = msg.topic
    payload = msg.payload
    _LOGGER.debug(f"Received metric update: topic={topic}, payload={payload}")

    # Parse the topic
    parts = topic.split('/')
    if len(parts) >= 5 and parts[0] == 'ovms' and parts[3] == 'metric':
        vehicle_name = parts[1]  # Dynamic vehicle name
        vin = parts[2]  # Dynamic VIN
        metric_key = '/'.join(parts[4:])  # Full metric key

        # Parse the payload (assuming JSON or plain text)
        try:
            value = json.loads(payload)
        except json.JSONDecodeError:
            value = payload

        # Create or update the sensor entity
        update_sensor_entity(hass, vin, metric_key, value)

def handle_notification_update(hass: HomeAssistant, msg):
    """Handle incoming MQTT messages for notifications."""
    topic = msg.topic
    payload = msg.payload
    _LOGGER.debug(f"Received notification: topic={topic}, payload={payload}")

    # Parse the topic
    parts = topic.split('/')
    if len(parts) >= 5 and parts[0] == 'ovms' and parts[3] == 'notify':
        vehicle_name = parts[1]  # Dynamic vehicle name
        vin = parts[2]  # Dynamic VIN
        notification_type = '/'.join(parts[4:])  # Full notification type

        # Log the notification (or trigger an automation)
        _LOGGER.info(f"Notification received for {vin}: {notification_type} = {payload}")

def update_sensor_entity(hass: HomeAssistant, vin: str, metric_key: str, value):
    """Create or update a sensor entity."""
    entity_id = f"sensor.{vin}_{metric_key.replace('/', '_')}"
    entities = hass.data[DOMAIN]['entities']

    if entity_id not in entities:
        # Create a new sensor entity
        sensor = OvmsSensor(vin, metric_key, value)
        entities[entity_id] = sensor
        hass.add_job(sensor.async_add_to_platform, hass, None)
        _LOGGER.debug(f"Created new entity: {entity_id}")
    else
