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

# Common OVMS metric patterns and friendly names
METRIC_PATTERNS = {
    "v/b/soc": "Battery State of Charge",
    "v/b/range/est": "Estimated Range",
    "v/b/12v/voltage": "12V Battery Voltage",
    "v/b/p/temp/avg": "Battery Temperature",
    "xvu/b/soc/abs": "Absolute Battery SOC",
    "xvu/b/soh/vw": "Battery Health",
    "v/p/latitude": "Latitude",
    "v/p/longitude": "Longitude",
    "v/p/odometer": "Odometer",
    "v/p/gpssq": "GPS Signal Quality",
    "v/c/limit/soc": "Charge Limit",
    "v/c/duration/full": "Full Charge Duration",
    "xvu/c/eff/calc": "Charging Efficiency",
    "xvu/c/ac/p": "AC Charging Power",
    "xvu/e/hv/chgmode": "Charging Mode",
    "v/e/batteryage": "Battery Age",
}

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
        'entities': {},         # All created entities 
        'config': config,       # Config data
        'discovered_vehicles': {},  # vehicle_id to username mapping
    }
    
    _LOGGER.info(f"OVMS MQTT using prefix: {topic_prefix}, QoS: {qos}")
    
    # Create MQTT message handler
    @callback
    def handle_mqtt_message(msg):
        """Handle all MQTT messages."""
        topic = msg.topic
        
        # Convert payload to string
        try:
            payload_str = msg.payload.decode('utf-8').strip()
        except (UnicodeDecodeError, AttributeError):
            payload_str = str(msg.payload).strip()
        
        _LOGGER.debug(f"MQTT message received: {topic} = {payload_str}")
        
        # Process message based on topic type
        if "/metric/" in topic:
            process_metric_message(hass, topic, payload_str, async_add_entities)
        elif "/notify/" in topic:
            process_notification(hass, topic, payload_str, async_add_entities)
        elif "/client/" in topic:
            process_client_message(hass, topic, payload_str, async_add_entities)
    
    # Function to process metric messages
    def process_metric_message(hass, topic, payload_str, async_add_entities):
        """Process an MQTT metric message."""
        _LOGGER.info(f"Processing metric: {topic}")
        
        # Extract parts from topic (format: prefix/username/vehicle_id/metric/path)
        parts = topic.split('/')
        
        if len(parts) >= 5 and "metric" in parts:
            username = parts[1]
            vehicle_id = parts[2]
            metric_index = parts.index("metric")
            
            # Extract the metric path (everything after "metric")
            if metric_index < len(parts) - 1:
                metric_path = '/'.join(parts[metric_index+1:])
                
                # Store discovered vehicle_id and username
                if vehicle_id not in hass.data[DOMAIN]['discovered_vehicles']:
                    _LOGGER.info(f"New vehicle discovered: {vehicle_id} (username: {username})")
                    hass.data[DOMAIN]['discovered_vehicles'][vehicle_id] = username
                
                _LOGGER.info(f"Parsed: vehicle_id={vehicle_id}, metric={metric_path}")
                
                # Parse payload value
                value = parse_value(payload_str)
                
                # Create or update entity
                create_or_update_entity(hass, vehicle_id, metric_path, value, topic, async_add_entities)
    
    # Process notification messages
    def process_notification(hass, topic, payload_str, async_add_entities):
        """Process notification messages."""
        parts = topic.split('/')
        
        if len(parts) >= 4 and "notify" in parts:
            vehicle_id = parts[2]
            notify_index = parts.index("notify")
            notification_type = '/'.join(parts[notify_index + 1:]) if notify_index < len(parts) - 1 else ""
            
            _LOGGER.info(f"Notification: vehicle_id={vehicle_id}, type={notification_type}, message={payload_str}")
            
            # Create a notification entity
            entity_id = f"notification_{slugify(notification_type)}"
            unique_id = f"ovms_{slugify(vehicle_id)}_{entity_id}"
            
            if unique_id not in hass.data[DOMAIN]['entities']:
                _LOGGER.info(f"Creating notification entity: {unique_id}")
                sensor = OvmsSensor(vehicle_id, f"notify/{notification_type}", payload_str, topic, 
                                   f"Notification {notification_type.replace('/', ' ').title()}")
                hass.data[DOMAIN]['entities'][unique_id] = sensor
                async_add_entities([sensor])
            else:
                hass.data[DOMAIN]['entities'][unique_id].update_value(payload_str)
    
    # Process client messages (commands and responses)
    def process_client_message(hass, topic, payload_str, async_add_entities):
        """Process client command/response messages."""
        parts = topic.split('/')
        
        if len(parts) >= 5 and "client" in parts:
            vehicle_id = parts[2]
            client_id = parts[4] if len(parts) > 4 else "unknown"
            
            if "command" in parts:
                _LOGGER.debug(f"Client command: vehicle_id={vehicle_id}, client={client_id}")
            elif "response" in parts:
                _LOGGER.debug(f"Client response: vehicle_id={vehicle_id}, client={client_id}")
            elif "active" in parts:
                _LOGGER.info(f"Client active: vehicle_id={vehicle_id}, client={client_id}, status={payload_str}")
                
                # Create client status entity
                unique_id = f"ovms_{slugify(vehicle_id)}_client_{slugify(client_id)}_status"
                
                if unique_id not in hass.data[DOMAIN]['entities']:
                    _LOGGER.info(f"Creating client status entity: {unique_id}")
                    sensor = OvmsSensor(vehicle_id, f"client/{client_id}/status", payload_str, topic,
                                       f"Client {client_id} Status")
                    hass.data[DOMAIN]['entities'][unique_id] = sensor
                    async_add_entities([sensor])
                else:
                    hass.data[DOMAIN]['entities'][unique_id].update_value(payload_str)
    
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
    
    # Create or update entity
    def create_or_update_entity(hass, vehicle_id, metric_path, value, topic, async_add_entities):
        """Create or update an entity for a specific vehicle_id and metric."""
        
        # Create a unique_id for this entity
        unique_id = f"ovms_{slugify(vehicle_id)}_{slugify(metric_path)}"
        
        if unique_id in hass.data[DOMAIN]['entities']:
            # Entity already exists, update it
            _LOGGER.debug(f"Updating existing entity: {unique_id} = {value}")
            hass.data[DOMAIN]['entities'][unique_id].update_value(value)
        else:
            # Create new entity with friendly name
            friendly_name = get_friendly_name(metric_path)
            _LOGGER.info(f"Creating new entity: {unique_id} ({friendly_name})")
            
            sensor = OvmsSensor(vehicle_id, metric_path, value, topic, friendly_name)
            hass.data[DOMAIN]['entities'][unique_id] = sensor
            async_add_entities([sensor])
    
    def get_friendly_name(metric_path):
        """Get a friendly name for a metric based on known patterns."""
        # Direct lookup in patterns dictionary
        if metric_path in METRIC_PATTERNS:
            return METRIC_PATTERNS[metric_path]
            
        # Try matching with wildcards for partial metric paths
        for pattern, name in METRIC_PATTERNS.items():
            if metric_path.endswith(pattern) or pattern.endswith(metric_path):
                return name
                
        # Default: convert path to title case with spaces
        return metric_path.replace('/', ' ').title()
    
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

    def __init__(self, vehicle_id, metric_key, value, topic, friendly_name=None):
        """Initialize the sensor."""
        super().__init__()
        self._vehicle_id = vehicle_id
        self._metric_key = metric_key
        self._topic = topic
        self._attr_native_value = value
        self._friendly_name = friendly_name
        
        # Create a unique ID
        self._attr_unique_id = f"ovms_{slugify(vehicle_id)}_{slugify(metric_key)}"
        
        # Make a user-friendly name
        if friendly_name:
            self._attr_name = f"OVMS {vehicle_id} {friendly_name}"
        else:
            self._attr_name = f"OVMS {vehicle_id} {metric_key.replace('/', ' ').title()}"
        
        # Set attributes
        self._attr_available = True
        self._attr_extra_state_attributes = {
            "vehicle_id": vehicle_id,
            "metric_key": metric_key,
            "mqtt_topic": topic,
            "source": "OVMS MQTT Integration"
        }
        
        _LOGGER.debug(f"Initialized entity: {self._attr_unique_id}")
    
    @property
    def device_info(self):
        """Return device info for this sensor."""
        return {
            "identifiers": {(DOMAIN, self._vehicle_id)},
            "name": f"OVMS Vehicle {self._vehicle_id}",
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
