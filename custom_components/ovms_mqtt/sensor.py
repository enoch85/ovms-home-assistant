import logging
import json
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import Entity
from homeassistant.components import mqtt
from .const import DOMAIN, CONF_BROKER, CONF_PORT, CONF_USERNAME, CONF_PASSWORD, CONF_TOPIC_PREFIX, CONF_QOS

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up OVMS MQTT sensor platform from a config entry."""
    _LOGGER.debug("Starting async_setup_entry for OVMS MQTT sensor platform")

    config = entry.data
    topic_prefix = config.get(CONF_TOPIC_PREFIX, "ovms")
    qos = config.get(CONF_QOS, 1)

    _LOGGER.debug(f"Configuration loaded: topic_prefix={topic_prefix}, qos={qos}")

    # Initialize entities dictionary
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    
    hass.data[DOMAIN] = {
        'entities': {},
        'config': config,
        'discovered_topics': set()
    }
    _LOGGER.debug("Configuration stored in hass.data")

    # Create a callback for handling the MQTT subscription
    @callback
    def message_received(msg):
        """Handle received MQTT messages."""
        topic = msg.topic
        payload = msg.payload
        
        try:
            payload_str = payload.decode('utf-8')
        except (UnicodeDecodeError, AttributeError):
            payload_str = str(payload)
            
        _LOGGER.debug(f"Received MQTT message: topic={topic}, payload={payload_str}")
        
        # Detect if this is a metric or notification topic
        if "/metric/" in topic:
            handle_metric_update(hass, topic, payload_str, async_add_entities)
        elif "/notify/" in topic:
            handle_notification_update(hass, topic, payload_str)
            
    # Subscribe to all OVMS MQTT topics with wildcard
    subscription = await mqtt.async_subscribe(
        hass, 
        f"{topic_prefix}/#", 
        message_received, 
        qos
    )
    
    _LOGGER.debug(f"Subscribed to MQTT topic: {topic_prefix}/#")
    
    # Store the subscription for later cleanup
    hass.data[DOMAIN]['subscription'] = subscription
    
    return True

def handle_metric_update(hass: HomeAssistant, topic: str, payload_str: str, async_add_entities: AddEntitiesCallback):
    """Handle incoming MQTT messages for metrics."""
    _LOGGER.debug(f"Processing metric topic: {topic}")

    config = hass.data[DOMAIN]['config']
    topic_prefix = config.get(CONF_TOPIC_PREFIX, "ovms")

    parts = topic.split('/')
    
    # Validate topic structure
    if len(parts) < 5 or parts[0] != topic_prefix or "metric" not in parts:
        _LOGGER.warning(f"Topic does not match expected structure: {topic}")
        return
        
    # Find the position of "metric" in the topic
    try:
        metric_index = parts.index("metric")
        if metric_index < 3:  # Need at least prefix/vehicle/vin before metric
            _LOGGER.warning(f"Topic structure is invalid: {topic}")
            return
            
        vehicle_name = parts[1]  # Dynamic vehicle name
        vin = parts[2]  # Dynamic VIN
        metric_key = '/'.join(parts[metric_index+1:])  # Full metric key after "metric"
        
        _LOGGER.debug(f"Parsed metric: vehicle_name={vehicle_name}, vin={vin}, metric_key={metric_key}")
        
        # Parse the payload
        try:
            value = json.loads(payload_str)
            _LOGGER.debug(f"Payload parsed as JSON: {value}")
        except json.JSONDecodeError:
            # Try to convert to appropriate type
            value = payload_str.strip()
            try:
                # Convert to number if possible
                if '.' in value:
                    value = float(value)
                else:
                    value = int(value)
            except ValueError:
                # Keep as string if not a number
                pass
            _LOGGER.debug(f"Payload processed as: {value} (type: {type(value)})")
        
        # Create or update the sensor entity
        update_sensor_entity(hass, vin, metric_key, value, async_add_entities)
        
    except ValueError:
        _LOGGER.warning(f"Could not find 'metric' in topic: {topic}")
        return

def handle_notification_update(hass: HomeAssistant, topic: str, payload_str: str):
    """Handle incoming MQTT messages for notifications."""
    _LOGGER.debug(f"Processing notification topic: {topic}")

    config = hass.data[DOMAIN]['config']
    topic_prefix = config.get(CONF_TOPIC_PREFIX, "ovms")

    parts = topic.split('/')
    
    # Find the position of "notify" in the topic
    try:
        notify_index = parts.index("notify")
        if notify_index < 3:  # Need at least prefix/vehicle/vin before notify
            _LOGGER.warning(f"Topic structure is invalid: {topic}")
            return
            
        vehicle_name = parts[1]  # Dynamic vehicle name
        vin = parts[2]  # Dynamic VIN
        notification_type = '/'.join(parts[notify_index+1:])  # Full notification type
        
        _LOGGER.info(f"Notification received for {vin}: {notification_type} = {payload_str}")
        
    except ValueError:
        _LOGGER.warning(f"Could not find 'notify' in topic: {topic}")
        return

def update_sensor_entity(hass: HomeAssistant, vin: str, metric_key: str, value, async_add_entities: AddEntitiesCallback):
    """Create or update a sensor entity."""
    # Create a safe entity_id (remove invalid characters)
    safe_metric_key = metric_key.replace('/', '_').replace('.', '_')
    entity_id = f"{vin}_{safe_metric_key}"
    
    _LOGGER.debug(f"Updating sensor entity: entity_id={entity_id}, value={value}")
    
    # Initialize entities dict if needed
    if 'entities' not in hass.data[DOMAIN]:
        hass.data[DOMAIN]['entities'] = {}
    
    entities = hass.data[DOMAIN]['entities']

    if entity_id not in entities:
        # Create a new sensor entity
        _LOGGER.debug(f"Creating new sensor entity: {entity_id}")
        sensor = OvmsSensor(vin, metric_key, value)
        entities[entity_id] = sensor
        async_add_entities([sensor], True)  # True for update before adding
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
        # Make sure the unique_id is valid
        safe_metric_key = metric_key.replace('/', '_').replace('.', '_')
        self._unique_id = f"{vin}_{safe_metric_key}"
        self._name = f"OVMS {vin} {metric_key.replace('/', ' ')}"
        
        # Initialize additional attributes
        self._attr_available = True
        self._attr_extra_state_attributes = {
            "vin": vin,
            "metric_key": metric_key
        }
        
        _LOGGER.debug(f"Created sensor with unique_id={self._unique_id}, name={self._name}")

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
        
    @property
    def extra_state_attributes(self):
        """Return entity specific state attributes."""
        return self._attr_extra_state_attributes

    def update_value(self, value):
        """Update the sensor's value."""
        _LOGGER.debug(f"Updating sensor value: old={self._value} new={value}")
        self._value = value
        self.async_write_ha_state()  # Use async_write_ha_state instead of schedule_update_ha_state
        _LOGGER.debug("Sensor value updated and state written")
