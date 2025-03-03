import logging
import json
import re
from datetime import timedelta
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import SensorEntity
from homeassistant.components import mqtt
from homeassistant.util import slugify
from .const import DOMAIN, CONF_BROKER, CONF_PORT, CONF_USERNAME, CONF_PASSWORD, CONF_TOPIC_PREFIX, CONF_QOS

_LOGGER = logging.getLogger(__name__)

# Topic patterns to match for different OVMS metrics
TOPIC_PATTERNS = [
    # Pattern for battery state of charge
    r".*/metric/v/b/soc$",
    # Pattern for location
    r".*/metric/v/p/(latitude|longitude)$",
    # Pattern for odometer
    r".*/metric/v/p/odometer$",
    # Pattern for range estimation
    r".*/metric/v/b/range/.*$",
    # Pattern for temperatures
    r".*/metric/v/b/p/temp/.*$",
    # Pattern for any metric
    r".*/metric/.*$",
    # Pattern for notifications
    r".*/notify/.*$"
]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up OVMS MQTT sensor platform from a config entry."""
    _LOGGER.info("Starting OVMS MQTT sensor platform setup")

    config = entry.data
    topic_prefix = config.get(CONF_TOPIC_PREFIX, "ovms")
    qos = config.get(CONF_QOS, 1)

    # Initialize our data structure
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    
    hass.data[DOMAIN] = {
        'entities': {},
        'config': config,
        'discovered_topics': set(),
        'pending_entities': set()
    }
    
    _LOGGER.info(f"OVMS MQTT configured with prefix: {topic_prefix}, QoS: {qos}")

    # Create a callback for handling the MQTT subscription
    @callback
    def message_received(msg):
        """Handle received MQTT messages."""
        try:
            topic = msg.topic
            
            # Store discovered topic
            hass.data[DOMAIN]['discovered_topics'].add(topic)
            
            try:
                payload_str = msg.payload.decode('utf-8').strip()
            except (UnicodeDecodeError, AttributeError):
                payload_str = str(msg.payload).strip()
                
            _LOGGER.info(f"MQTT message received: {topic} = {payload_str}")
            
            # Process the message based on topic structure
            if "/metric/" in topic:
                handle_metric_update(hass, topic, payload_str, async_add_entities)
            elif "/notify/" in topic:
                handle_notification_update(hass, topic, payload_str)
                
        except Exception as e:
            _LOGGER.error(f"Error processing MQTT message: {e}")
    
    # Subscribe to all OVMS MQTT topics with wildcard
    try:
        _LOGGER.info(f"Subscribing to MQTT topic: {topic_prefix}/#")
        subscription = await mqtt.async_subscribe(
            hass, 
            f"{topic_prefix}/#", 
            message_received, 
            qos
        )
        hass.data[DOMAIN]['subscription'] = subscription
        _LOGGER.info("MQTT subscription successful")
    except Exception as e:
        _LOGGER.error(f"Failed to subscribe to MQTT: {e}")
    
    # Schedule regular discovery checks
    async def check_discovered_topics(now=None):
        """Check for newly discovered topics and create entities."""
        discovered = hass.data[DOMAIN]['discovered_topics']
        entities_to_add = []
        
        _LOGGER.debug(f"Checking {len(discovered)} discovered topics")
        
        for topic in discovered:
            # Check if we need to create an entity for this topic
            if any(re.match(pattern, topic) for pattern in TOPIC_PATTERNS):
                _LOGGER.info(f"Creating entity for discovered topic: {topic}")
                try:
                    parts = topic.split('/')
                    if "metric" in parts:
                        metric_index = parts.index("metric")
                        # Need at least 2 parts before metric (usually device and VIN)
                        if metric_index >= 2:
                            vin = parts[metric_index-1]  # VIN is typically right before "metric"
                            metric_key = '/'.join(parts[metric_index+1:])
                            
                            # Create unique ID
                            unique_id = f"{slugify(vin)}_{slugify(metric_key)}"
                            
                            if (unique_id not in hass.data[DOMAIN]['entities'] and 
                                unique_id not in hass.data[DOMAIN]['pending_entities']):
                                
                                sensor = OvmsSensor(vin, metric_key, None, topic)
                                hass.data[DOMAIN]['entities'][unique_id] = sensor
                                hass.data[DOMAIN]['pending_entities'].add(unique_id)
                                entities_to_add.append(sensor)
                                _LOGGER.info(f"Created entity for topic: {topic} → {unique_id}")
                            
                except ValueError as e:
                    _LOGGER.warning(f"Could not parse topic: {topic} - {str(e)}")
                except Exception as e:
                    _LOGGER.error(f"Error creating entity for topic {topic}: {str(e)}")
        
        # Register the new entities with Home Assistant
        if entities_to_add:
            _LOGGER.info(f"Adding {len(entities_to_add)} new entities to Home Assistant")
            async_add_entities(entities_to_add)
    
    # Initial discovery attempt with basic fallback topics
    fallback_topics = [
        f"{topic_prefix}/+/+/metric/v/b/soc",
        f"{topic_prefix}/+/+/metric/v/p/latitude",
        f"{topic_prefix}/+/+/metric/v/p/longitude",
        f"{topic_prefix}/+/+/metric/v/p/odometer"
    ]
    
    for topic in fallback_topics:
        _LOGGER.info(f"Creating fallback subscription for topic pattern: {topic}")
        await mqtt.async_subscribe(hass, topic, message_received, qos)
    
    # Register a periodic callback to check for new topics
    hass.helpers.event.async_track_time_interval(
        check_discovered_topics, 
        timedelta(seconds=60)  # Check every minute
    )
    
    # Run initial check immediately
    await check_discovered_topics()
    
    return True

def handle_metric_update(hass: HomeAssistant, topic: str, payload_str: str, async_add_entities: AddEntitiesCallback):
    """Handle incoming MQTT messages for metrics."""
    _LOGGER.debug(f"Processing metric topic: {topic}")

    try:
        parts = topic.split('/')
        metric_index = parts.index("metric")
        
        if metric_index < 2:
            _LOGGER.warning(f"Invalid topic structure, not enough parts before 'metric': {topic}")
            return
            
        vin = parts[metric_index-1]  # VIN is typically right before "metric"
        metric_key = '/'.join(parts[metric_index+1:])
        
        _LOGGER.debug(f"Parsed metric: vin={vin}, metric={metric_key}")
        
        # Parse payload value
        value = parse_payload(payload_str)
        
        # Create or update entity
        update_sensor_entity(hass, vin, metric_key, value, topic, async_add_entities)
            
    except ValueError:
        _LOGGER.warning(f"Could not find 'metric' in topic: {topic}")
    except Exception as e:
        _LOGGER.error(f"Error processing metric update: {str(e)}")

def handle_notification_update(hass: HomeAssistant, topic: str, payload_str: str):
    """Handle incoming MQTT messages for notifications."""
    _LOGGER.debug(f"Notification topic: {topic}")
    # Process notifications here if needed

def parse_payload(payload_str: str):
    """Parse payload string into appropriate data type."""
    if not payload_str:
        return None
        
    # Try boolean
    if payload_str.lower() in ('true', 'false'):
        return payload_str.lower() == 'true'
        
    # Try number
    try:
        if '.' in payload_str:
            return float(payload_str)
        else:
            return int(payload_str)
    except ValueError:
        pass
        
    # Try JSON
    try:
        return json.loads(payload_str)
    except json.JSONDecodeError:
        pass
        
    # Return as string
    return payload_str

def update_sensor_entity(hass: HomeAssistant, vin: str, metric_key: str, value, topic: str, async_add_entities: AddEntitiesCallback):
    """Create or update a sensor entity."""
    # Create a valid unique_id
    unique_id = f"{slugify(vin)}_{slugify(metric_key)}"
    
    _LOGGER.debug(f"Processing entity: {unique_id} with value: {value}")
    
    entities = hass.data[DOMAIN]['entities']
    pending = hass.data[DOMAIN].get('pending_entities', set())

    if unique_id not in entities and unique_id not in pending:
        # Create a new sensor entity
        _LOGGER.info(f"Creating new entity: {unique_id}")
        sensor = OvmsSensor(vin, metric_key, value, topic)
        entities[unique_id] = sensor
        hass.data[DOMAIN]['pending_entities'].add(unique_id)
        
        # Add the entity to Home Assistant
        async_add_entities([sensor])
    elif unique_id in entities:
        # Update existing entity
        _LOGGER.debug(f"Updating existing entity: {unique_id} = {value}")
        entities[unique_id].update_value(value)


class OvmsSensor(SensorEntity):
    """Representation of an OVMS MQTT sensor."""

    def __init__(self, vin: str, metric_key: str, value, topic: str):
        """Initialize the sensor."""
        super().__init__()
        self._vin = vin
        self._metric_key = metric_key
        self._topic = topic
        self._attr_native_value = value
        
        # Create slugified IDs for Home Assistant compatibility
        self._attr_unique_id = f"{slugify(vin)}_{slugify(metric_key)}"
        
        # Determine entity name - try to make it user-friendly
        friendly_metric = metric_key.replace('/', ' ').title()
        self._attr_name = f"{vin} {friendly_metric}"
        
        # Set entity attributes
        self._attr_available = True
        self._attr_extra_state_attributes = {
            "vin": vin,
            "metric_key": metric_key,
            "mqtt_topic": topic,
            "source": "OVMS MQTT Integration"
        }
        
        _LOGGER.info(f"Initialized entity: {self._attr_unique_id} for topic {topic}")
        
    @property
    def device_info(self):
        """Return device info for this sensor."""
        return {
            "identifiers": {(DOMAIN, self._vin)},
            "name": f"OVMS Vehicle {self._vin}",
            "manufacturer": "Open Vehicle Monitoring System",
            "model": "OVMS",
            "sw_version": "1.0.0",
        }

    def update_value(self, value):
        """Update the sensor's value."""
        old_value = self._attr_native_value
        self._attr_native_value = value
        
        if old_value != value:
            _LOGGER.info(f"Updated {self._attr_unique_id}: {old_value} → {value}")
            
        self.async_write_ha_state()
