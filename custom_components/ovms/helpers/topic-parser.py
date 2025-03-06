"""Topic parsing utilities for OVMS integration."""
import logging
from typing import Dict, List, Optional, Tuple, Any

from ..const import LOGGER_NAME
from ..metrics import (
    METRIC_DEFINITIONS,
    TOPIC_PATTERNS,
    BINARY_METRICS,
    get_metric_by_path,
    get_metric_by_pattern,
    determine_category_from_topic,
    create_friendly_name,
)

_LOGGER = logging.getLogger(LOGGER_NAME)

class OVMSTopicParser:
    """Helper class for OVMS topic parsing."""
    
    @staticmethod
    def parse_topic(topic: str, structure_prefix: str) -> Tuple[Optional[str], Optional[Dict]]:
        """Parse a topic to determine the entity type and info.
        
        Args:
            topic: The MQTT topic to parse
            structure_prefix: The structure prefix configured for this OVMS instance
            
        Returns:
            A tuple of (entity_type, entity_info) where entity_type is one of
            'sensor', 'binary_sensor', 'switch', 'device_tracker', or None if
            the topic cannot be parsed, and entity_info is a dictionary with
            entity information or None if parsing failed.
        """
        _LOGGER.debug("Parsing topic: %s", topic)
        
        # Check if topic matches our structure prefix
        if not topic.startswith(structure_prefix):
            _LOGGER.debug("Topic does not match structure prefix: %s", structure_prefix)
            return None, None
            
        # Remove the structure prefix
        topic_suffix = topic[len(structure_prefix):].lstrip('/')
        _LOGGER.debug("Topic suffix after removing prefix: %s", topic_suffix)
        
        # Split the remaining path into parts
        parts = topic_suffix.split("/")
        _LOGGER.debug("Topic parts: %s", parts)
        
        if len(parts) < 2:
            _LOGGER.debug("Topic has too few parts: %s", parts)
            return None, None
        
        # Check if this is a command/response topic - don't create entities for these
        if ('client/rr/command' in topic_suffix or 'client/rr/response' in topic_suffix):
            _LOGGER.debug("Skipping command/response topic: %s", topic)
            return None, None
            
        return OVMSTopicParser._determine_entity_type(topic, topic_suffix, parts)
    
    @staticmethod
    def _determine_entity_type(topic: str, topic_suffix: str, parts: List[str]) -> Tuple[Optional[str], Optional[Dict]]:
        """Determine the entity type and info from topic parts.
        
        Args:
            topic: The original topic
            topic_suffix: The topic with the prefix removed
            parts: The topic split into parts
            
        Returns:
            Tuple of (entity_type, entity_info)
        """
        # Try to match with known metric patterns
        # First, check if this is a standard OVMS metric
        metric_path = topic_suffix.replace("/", ".")
        metric_info = get_metric_by_path(metric_path)
        
        # If no exact match, try to match by patterns
        if not metric_info:
            metric_info = get_metric_by_pattern(parts)
        
        # Determine entity type and category
        entity_type = "sensor"  # Default type
        category = determine_category_from_topic(parts)
        name = "_".join(parts)
        
        # Check if this is a binary sensor
        is_binary = OVMSTopicParser._is_binary_sensor(metric_path, name, metric_info)
        if is_binary:
            entity_type = "binary_sensor"
        
        # Check for location/GPS data
        if OVMSTopicParser._is_location_data(name, category):
            entity_type = "device_tracker"
        
        # Check for commands/switches
        if OVMSTopicParser._is_switch(parts, name):
            entity_type = "switch"
        
        # Create friendly name
        friendly_name = create_friendly_name(parts, metric_info)
        
        # Prepare attributes
        attributes = {
            "topic": topic,
            "category": category,
            "parts": parts,
        }
        
        # Add additional attributes from metric definition
        if metric_info:
            # Only add attributes that aren't already in the entity definition
            for k, v in metric_info.items():
                if k not in ["name", "device_class", "state_class", "unit"]:
                    attributes[k] = v
        
        # Create the entity info
        entity_info = {
            "name": name,
            "friendly_name": friendly_name,
            "attributes": attributes,
        }
            
        _LOGGER.debug("Parsed topic as: type=%s, name=%s, category=%s, friendly_name=%s", 
                    entity_type, entity_info['name'], category, entity_info['friendly_name'])
        return entity_type, entity_info
    
    @staticmethod
    def _is_binary_sensor(metric_path: str, name: str, metric_info: Optional[Dict]) -> bool:
        """Determine if this topic should be a binary sensor.
        
        Args:
            metric_path: The metric path in dot notation
            name: The entity name
            metric_info: Metric info if available
            
        Returns:
            True if this should be a binary sensor, False otherwise
        """
        # Check if this has a binary sensor device class from metric info
        if metric_info and "device_class" in metric_info:
            from homeassistant.components.binary_sensor import BinarySensorDeviceClass
            # Check if the device class is from binary_sensor
            if hasattr(metric_info["device_class"], "__module__") and "binary_sensor" in metric_info["device_class"].__module__:
                return True
        
        # Also check if this is a known binary metric or has binary pattern in name
        if metric_path in BINARY_METRICS or any(binary_pattern in name.lower() for binary_pattern in 
                                            ["on", "active", "enabled", "running", "connected", "locked", "door", "charging"]):
            return True
            
        return False
    
    @staticmethod
    def _is_location_data(name: str, category: str) -> bool:
        """Determine if this topic contains location data.
        
        Args:
            name: The entity name
            category: The entity category
            
        Returns:
            True if this contains location data, False otherwise
        """
        # If both latitude and longitude are in the topic, it's likely a location
        if "latitude" in name.lower() and "longitude" in name.lower():
            return True
            
        # If it's in the location category and has gps in the name
        if category == "location" and ("gps" in name.lower() or "position" in name.lower()):
            return True
            
        return False
    
    @staticmethod
    def _is_switch(parts: List[str], name: str) -> bool:
        """Determine if this topic should be a switch.
        
        Args:
            parts: The topic parts
            name: The entity name
            
        Returns:
            True if this should be a switch, False otherwise
        """
        if "command" in parts:
            return True
            
        if any(switch_pattern in name.lower() for switch_pattern in 
              ["switch", "toggle", "set", "enable", "disable", "control"]):
            return True
            
        return False
