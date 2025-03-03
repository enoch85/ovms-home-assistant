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

# Common OVMS topics to pre-create
COMMON_TOPICS = [
    "v/b/soc",                # Battery State of Charge
    "v/p/latitude",           # Vehicle Latitude
    "v/p/longitude",          # Vehicle Longitude
    "v/p/odometer",           # Vehicle Odometer
    "v/b/range/est",          # Estimated Range
    "v/b/p/temp/avg",         # Battery Temperature
    "v/c/limit/soc",          # Charge Limit
    "v/b/12v/voltage",        # 12V Battery Voltage
    "v/c/duration/full",      # Full charge duration
    "xvu/c/eff/calc",         # Charging efficiency
    "xvu/b/soc/abs",          # Absolute SOC
    "xvu/e/hv/chgmode",       # Charging mode
    "xvu/b/soh/vw",           # Battery health
    "v/e/batteryage"          # Battery age
]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up OVMS MQTT sensor platform from a config entry."""
    _LOGGER.info("Setting up OVMS MQTT sensor platform")

    config = entry.data
    topic_prefix = config.get(CONF_TOPIC_PREFIX, "ovms")
    qos = config.get(CONF_QOS, 1)

    # Initialize data structure
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    
    hass.data[DOMAIN] = {
        'entities': {},
        'config': config,
        'discovered_topics': set(),
    }
    
    _LOGGER.info(f"OVMS MQTT using prefix: {topic_prefix}, QoS: {qos}")
    
    # Create initial entities (these will show up immediately)
    entities_to_add = []
    
    # Pre-create entities for common metrics
    for topic_suffix in COMMON_TOPICS:
        # Create placeholder entities for common topics
        _LOGGER.debug(f"Pre-creating entity for common topic: {topic_suffix}")
        
        # Use a generic VIN until we detect the actual one
        vin = "VEHICLE"
        metric_key = topic_suffix
        
        # Create a unique_id
        unique_id = f"ovms_{slugify(vin)}_{slugify(metric_key)}"
        
        # Create the entity
        sensor = OvmsSensor(vin, metric_key, None, f"{topic_prefix}/+/+/metric/{topic_suffix}")
        hass.data[DOMAIN]['entities'][unique_id] = sensor
        entities_to_add.append(sensor)
    
    # Add the pre-created entities
    if entities_to_add:
        _LOGGER.info(f"Adding {len(entities_to_add)} pre-created entities")
        async_add_entities(entities_to_add)

    # Create MQTT message handler
    @callback
    def handle_mqtt_message(msg):
        """Handle all MQTT messages."""
        topic = msg.topic
        
        # Store topic for discovery
        hass.data[DOMAIN]['discovered_topics'].add(topic)
        
        # Convert payload to string
        try:
            payload_str = msg.payload.decode('utf-8').strip()
        except (UnicodeDecodeError, AttributeError):
            payload_str = str(msg.payload).strip()
        
        _LOGGER.debug(f"MQTT message received: {topic} = {payload_str}")
        
        # Process message if it's a metric
        if "/metric/" in topic:
            process_metric(hass, topic, payload_str, async_add_entities)
        elif "/notify/" in topic:
            # For future implementation of notification handling
            _LOGGER.debug(f"Notification received: {topic} = {payload_str}")
    
    # Function to process metric messages
    def process_metric(hass, topic, payload_str, async_add_entities):
        """Process an MQTT metric message."""
        _LOGGER.debug(f"Processing metric: {topic}")
        
        # Extract parts from topic
        parts = topic.split('/')
        
        try:
            if "metric" in parts:
                metric_index = parts.index("metric")
                
                # Try to determine VIN - it's usually before "metric"
                if metric_index > 0:
                    # Assume VIN is the part before "metric"
                    vin = parts[metric_index - 1]
                    
                    # Extract metric key (everything after "metric")
                    if metric_index < len(parts) - 1:
                        metric_key = '/'.join(parts[metric_index + 1:])
                        
                        _LOGGER.debug(f"Parsed: VIN={vin}, metric={metric_key}")
                        
                        # Parse payload value
                        value = parse_value(payload_str)
                        
                        # Update or create entity
                        update_entity(hass, vin, metric_key, value, topic, async_add_entities)
                    else:
                        _LOGGER.debug(f"No metric key found after 'metric' in topic: {topic}")
                else:
                    _LOGGER.debug(f"No VIN found before 'metric' in topic: {topic}")
            else:
                _LOGGER.debug(f"No 'metric' part found in topic: {topic}")
                
                # Try alternative parsing for unusual formats
                match = re.search(r'([^/]+)/([^/]+)$', topic)
                if match:
                    # Use the last two parts as metric key
                    vin = "UNKNOWN"
                    metric_key = match.group(0)
                    
                    _LOGGER.debug(f"Alternative parsing: VIN={vin}, metric={metric_key}")
                    
                    # Parse payload value
                    value = parse_value(payload_str)
                    
                    # Update or create entity
                    update_entity(hass, vin, metric_key, value, topic, async_add_entities)
        except Exception as e:
            _LOGGER.error(f"Error processing metric {topic}: {str(e)}")
    
    # Parse payload value to appropriate type
    def parse_value(payload_str):
        """Parse payload string into appropriate type."""
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
    
    # Update existing entity or create new one
    def update_entity(hass, vin, metric_key, value, topic, async_add_entities):
        """Update existing entity or create new one."""
        _LOGGER.debug(f"Updating entity for VIN={vin}, metric={metric_key}, value={value}")
        
        # Try specific entity first
        specific_id = f"ovms_{slugify(vin)}_{slugify(metric_key)}"
        if specific_id in hass.data[DOMAIN]['entities']:
            _LOGGER.debug(f"Updating specific entity: {specific_id}")
            hass.data[DOMAIN]['entities'][specific_id].update_value(value)
            return True
            
        # Try generic entity with this metric key
        generic_id = f"ovms_vehicle_{slugify(metric_key)}"
        if generic_id in hass.data[DOMAIN]['entities']:
            _LOGGER.debug(f"Updating generic entity: {generic_id} and setting VIN to {vin}")
            hass.data[DOMAIN]['entities'][generic_id].update_value(value)
            hass.data[DOMAIN]['entities'][generic_id].update_vin(vin)
            return True
            
        # Create new entity if no match found
        _LOGGER.info(f"Creating new entity: {specific_id}")
        sensor = OvmsSensor(vin, metric_key, value, topic)
        hass.data[DOMAIN]['entities'][specific_id] = sensor
        async_add_entities([sensor])
        return True
    
    # Subscribe to all OVMS topics
    _LOGGER.info(f"Subscribing to all OVMS topics: {topic_prefix}/#")
    subscription = await mqtt.async_subscribe(
        hass, 
        f"{topic_prefix}/#", 
        handle_mqtt_message, 
        qos
    )
    
    # Store subscription for cleanup
    hass.data[DOMAIN]['subscription'] = subscription
    
    return True


class OvmsSensor(SensorEntity):
    """Representation of an OVMS MQTT sensor."""

    def __init__(self, vin, metric_key, value, topic):
        """Initialize the sensor."""
        super().__init__()
        self._vin = vin
        self._metric_key = metric_key
        self._topic = topic
        self._attr_native_value = value
        
        # Create a unique ID
        self._attr_unique_id = f"ovms_{slugify(vin)}_{slugify(metric_key)}"
        
        # Make a user-friendly name
        friendly_metric = metric_key.replace('/', ' ').title()
        self._attr_name = f"OVMS {vin} {friendly_metric}"
        
        # Set attributes
        self._attr_available = True
        self._attr_extra_state_attributes = {
            "vin": vin,
            "metric_key": metric_key,
            "mqtt_topic": topic,
            "source": "OVMS MQTT Integration"
        }
        
        _LOGGER.debug(f"Initialized entity: {self._attr_unique_id}")
    
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
            _LOGGER.debug(f"Updated {self._attr_unique_id}: {old_value} → {value}")
        
        self.async_write_ha_state()
    
    def update_vin(self, vin):
        """Update the VIN if this was a generic sensor."""
        if self._vin != vin and self._vin == "VEHICLE":
            _LOGGER.info(f"Updating entity VIN from {self._vin} to {vin}")
            self._vin = vin
            
            # Update the name
            friendly_metric = self._metric_key.replace('/', ' ').title()
            self._attr_name = f"OVMS {vin} {friendly_metric}"
            
            # Update attributes
            self._attr_extra_state_attributes["vin"] = vin
            
            self.async_write_ha_state()
