"""OVMS MQTT sensor platform."""
import logging
import json
import re
from typing import Any, Dict, List, Optional, Set, Callable
import asyncio

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import Entity
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_USERNAME, CONF_PASSWORD, CONF_SSL

from .const import (
    DOMAIN,
    CONF_TOPIC_PREFIX,
    CONF_VEHICLE_ID,
    CONF_QOS,
    DEFAULT_TOPIC_PREFIX,
    DEFAULT_VEHICLE_ID,
    DEFAULT_QOS,
    KNOWN_TOPICS,
    TOPIC_DISCOVERY_PATTERNS,
)

_LOGGER = logging.getLogger(__name__)

# Store discovered topics
DISCOVERED_TOPICS: Set[str] = set()

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> bool:
    """Set up OVMS MQTT sensor based on a config entry."""
    _LOGGER.debug("Setting up OVMS MQTT sensor platform")
    
    config = entry.data
    topic_prefix = config.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
    vehicle_id = config.get(CONF_VEHICLE_ID, DEFAULT_VEHICLE_ID)
    qos = config.get(CONF_QOS, DEFAULT_QOS)
    
    # Extract vehicle name and VIN from known topics
    vehicle_name = None
    vin = None
    
    # Try to extract vehicle_name and VIN from the first known topic
    for topic in KNOWN_TOPICS:
        parts = topic.split('/')
        if len(parts) >= 4:
            vehicle_name = parts[1]
            vin = parts[2]
            break
    
    # Fallback to default values if not found
    if not vehicle_name:
        vehicle_name = f"ovms-mqtt-{vehicle_id}"
    if not vin:
        vin = vehicle_id.upper()
    
    # Initialize data handler
    data_handler = OVMSDataHandler(
        hass, topic_prefix, vehicle_name, vin, qos, async_add_entities
    )
    
    # Store the data handler in hass.data
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    hass.data[DOMAIN][entry.entry_id] = data_handler
    
    # Start subscribing to topics
    await data_handler.async_subscribe_topics()
    
    return True


class OVMSDataHandler:
    """Handles MQTT subscriptions and entity updates for OVMS."""
    
    def __init__(
        self,
        hass: HomeAssistant,
        topic_prefix: str,
        vehicle_name: str,
        vin: str,
        qos: int,
        async_add_entities: AddEntitiesCallback,
    ) -> None:
        """Initialize the data handler."""
        self.hass = hass
        self.topic_prefix = topic_prefix
        self.vehicle_name = vehicle_name
        self.vin = vin
        self.qos = qos
        self.async_add_entities = async_add_entities
        self.entities: Dict[str, OVMSSensor] = {}
        self.subscriptions: List[Callable] = []
        self.discovery_subscriptions: List[Callable] = []
        
    async def async_subscribe_topics(self) -> None:
        """Subscribe to all relevant MQTT topics."""
        _LOGGER.debug(
            "Subscribing to OVMS MQTT topics: prefix=%s, vehicle=%s, VIN=%s",
            self.topic_prefix, self.vehicle_name, self.vin
        )
        
        # Subscribe to metric topics
        topic_filter = f"{self.topic_prefix}/{self.vehicle_name}/{self.vin}/metric/#"
        self.subscriptions.append(
            await mqtt.async_subscribe(
                self.hass,
                topic_filter,
                self._handle_metric_message,
                self.qos,
            )
        )
        _LOGGER.debug("Subscribed to metric topics: %s", topic_filter)
        
        # Subscribe to notification topics
        topic_filter = f"{self.topic_prefix}/{self.vehicle_name}/{self.vin}/notify/#"
        self.subscriptions.append(
            await mqtt.async_subscribe(
                self.hass,
                topic_filter,
                self._handle_notification_message,
                self.qos,
            )
        )
        _LOGGER.debug("Subscribed to notification topics: %s", topic_filter)
        
        # Start topic discovery
        await self._start_topic_discovery()
    
    async def _start_topic_discovery(self) -> None:
        """Start the discovery process for dynamic topics."""
        _LOGGER.debug("Starting topic discovery")
        
        # Subscribe to all topics for discovery
        for pattern in TOPIC_DISCOVERY_PATTERNS:
            topic_filter = pattern.format(
                prefix=self.topic_prefix,
                vehicle_name=self.vehicle_name,
                vin=self.vin
            )
            
            # Skip already subscribed patterns
            if topic_filter.endswith("#") and any(
                s.endswith("#") and topic_filter.startswith(s[:-1]) 
                for s in [f"{self.topic_prefix}/{self.vehicle_name}/{self.vin}/metric/#", 
                          f"{self.topic_prefix}/{self.vehicle_name}/{self.vin}/notify/#"]
            ):
                continue
                
            self.discovery_subscriptions.append(
                await mqtt.async_subscribe(
                    self.hass,
                    topic_filter,
                    self._handle_discovery_message,
                    self.qos,
                )
            )
            _LOGGER.debug("Subscribed to discovery topic: %s", topic_filter)
    
    @callback
    def _handle_discovery_message(self, msg) -> None:
        """Handle incoming MQTT messages for topic discovery."""
        topic = msg.topic
        
        # Skip if topic is already known
        if topic in DISCOVERED_TOPICS:
            return
            
        _LOGGER.debug("Discovered new topic: %s", topic)
        DISCOVERED_TOPICS.add(topic)
    
    @callback
    def _handle_metric_message(self, msg) -> None:
        """Handle incoming MQTT messages for metrics."""
        topic = msg.topic
        payload = msg.payload
        
        _LOGGER.debug("Received metric message: %s = %s", topic, payload)
        
        # Parse topic to extract the metric key
        parts = topic.split('/')
        if len(parts) >= 5 and parts[0] == self.topic_prefix and parts[3] == 'metric':
            metric_key = '/'.join(parts[4:])
            
            try:
                # Try to parse JSON payload
                try:
                    value = json.loads(payload)
                except json.JSONDecodeError:
                    # Use raw payload if not JSON
                    value = payload.decode('utf-8') if isinstance(payload, bytes) else payload
                
                # Create or update sensor entity
                self._update_sensor(metric_key, value)
                
            except Exception as e:
                _LOGGER.error("Error processing metric message: %s", e)
    
    @callback
    def _handle_notification_message(self, msg) -> None:
        """Handle incoming MQTT messages for notifications."""
        topic = msg.topic
        payload = msg.payload
        
        _LOGGER.debug("Received notification message: %s = %s", topic, payload)
        
        # Parse topic to extract the notification type
        parts = topic.split('/')
        if len(parts) >= 5 and parts[0] == self.topic_prefix and parts[3] == 'notify':
            notification_type = '/'.join(parts[4:])
            
            try:
                # Try to parse JSON payload
                try:
                    value = json.loads(payload)
                except json.JSONDecodeError:
                    # Use raw payload if not JSON
                    value = payload.decode('utf-8') if isinstance(payload, bytes) else payload
                
                # Create a notification sensor
                sensor_key = f"notify_{notification_type}"
                self._update_sensor(sensor_key, value)
                
                # For specific notifications, you could trigger events here
                self.hass.bus.async_fire(
                    f"{DOMAIN}_notification",
                    {"type": notification_type, "value": value, "vin": self.vin}
                )
                
            except Exception as e:
                _LOGGER.error("Error processing notification message: %s", e)
    
    def _update_sensor(self, key: str, value: Any) -> None:
        """Create or update a sensor entity."""
        # Generate unique ID for the sensor
        unique_id = f"{self.vin}_{key.replace('/', '_')}"
        
        if unique_id not in self.entities:
            # Create new sensor entity
            sensor = OVMSSensor(self.vin, key, value)
            self.entities[unique_id] = sensor
            self.async_add_entities([sensor])
            _LOGGER.debug("Created new sensor: %s", unique_id)
        else:
            # Update existing sensor
            self.entities[unique_id].update_value(value)
            _LOGGER.debug("Updated existing sensor: %s", unique_id)
    
    async def async_unsubscribe(self) -> None:
        """Unsubscribe from all MQTT topics."""
        for unsubscribe_cb in self.subscriptions:
            unsubscribe_cb()
        self.subscriptions = []
        
        for unsubscribe_cb in self.discovery_subscriptions:
            unsubscribe_cb()
        self.discovery_subscriptions = []
        
        _LOGGER.debug("Unsubscribed from all MQTT topics")


class OVMSSensor(SensorEntity):
    """Representation of an OVMS MQTT sensor."""
    
    def __init__(self, vin: str, key: str, value: Any) -> None:
        """Initialize the sensor."""
        self._vin = vin
        self._key = key
        self._attr_unique_id = f"{vin}_{key.replace('/', '_')}"
        
        # Generate user-friendly name
        name_parts = key.split('/')
        formatted_name = ' '.join(name_parts).title()
        self._attr_name = f"OVMS {vin} {formatted_name}"
        
        # Set initial state
        self._attr_native_value = self._process_value(value)
        
        # Determine unit of measurement and device class if possible
        self._attr_native_unit_of_measurement = self._determine_unit(key, value)
        self._attr_device_class = self._determine_device_class(key, value)
        
        _LOGGER.debug(
            "Initialized sensor: unique_id=%s, name=%s, value=%s, unit=%s, device_class=%s",
            self._attr_unique_id, self._attr_name, self._attr_native_value,
            self._attr_native_unit_of_measurement, self._attr_device_class
        )
    
    def _process_value(self, value: Any) -> Any:
        """Process the value for display."""
        # Handle JSON objects/arrays
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return value
    
    def _determine_unit(self, key: str, value: Any) -> Optional[str]:
        """Determine the unit of measurement based on the key and value."""
        key_lower = key.lower()
        
        # Temperature
        if 'temp' in key_lower or 'temperature' in key_lower:
            return "°C"
        
        # Voltage
        if 'voltage' in key_lower or key_lower.endswith('v'):
            return "V"
        
        # Current
        if 'current' in key_lower or key_lower.endswith('a'):
            return "A"
        
        # Power
        if 'power' in key_lower or key_lower.endswith('w'):
            return "W"
        
        # Energy
        if 'energy' in key_lower or 'kwh' in key_lower:
            return "kWh"
        
        # Percentage
        if 'soc' in key_lower or 'percent' in key_lower:
            return "%"
        
        # Distance
        if 'odometer' in key_lower or 'range' in key_lower or 'distance' in key_lower:
            return "km"
        
        # Speed
        if 'speed' in key_lower:
            return "km/h"
        
        # Duration
        if 'duration' in key_lower or 'time' in key_lower:
            return "min"
        
        # No recognized unit
        return None
    
    def _determine_device_class(self, key: str, value: Any) -> Optional[str]:
        """Determine the device class based on the key and value."""
        key_lower = key.lower()
        
        # Temperature
        if 'temp' in key_lower or 'temperature' in key_lower:
            return "temperature"
        
        # Voltage
        if 'voltage' in key_lower:
            return "voltage"
        
        # Current
        if 'current' in key_lower:
            return "current"
        
        # Power
        if 'power' in key_lower:
            return "power"
        
        # Energy
        if 'energy' in key_lower or 'kwh' in key_lower:
            return "energy"
        
        # Battery
        if 'soc' in key_lower or 'battery' in key_lower:
            return "battery"
        
        # No recognized device class
        return None
    
    def update_value(self, value: Any) -> None:
        """Update the sensor state."""
        self._attr_native_value = self._process_value(value)
        self.async_write_ha_state()
        _LOGGER.debug(
            "Updated sensor: unique_id=%s, new_value=%s",
            self._attr_unique_id, self._attr_native_value
        )
