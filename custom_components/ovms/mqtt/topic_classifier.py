"""Topic classification utilities for OVMS MQTT topics."""
from typing import Set, List
import re

from ..const import TopicTypes
from ..metrics.common.location import LOCATION_METRICS


class TopicClassifier:
    """Utility class for classifying OVMS topics by type and category."""
    
    @classmethod
    def is_coordinate_topic(cls, topic: str) -> bool:
        """Check if topic contains GPS coordinate data."""
        if not topic:
            return False
            
        topic_lower = topic.lower()
        parts = topic.split('/')
        
        # Direct keyword match in parts
        if any(part.lower() in TopicTypes.COORDINATE_KEYWORDS for part in parts):
            return True
            
        # Pattern matching for nested coordinate topics
        return any(f"/p/{keyword}" in topic_lower or f".p.{keyword}" in topic_lower 
                  for keyword in TopicTypes.COORDINATE_KEYWORDS)
    
    @classmethod
    def is_gps_quality_topic(cls, topic: str) -> bool:
        """Check if topic contains GPS quality metrics."""
        if not topic:
            return False
            
        topic_lower = topic.lower()
        return any(keyword in topic_lower for keyword in TopicTypes.GPS_QUALITY_KEYWORDS)
    
    @classmethod
    def is_version_topic(cls, topic: str) -> bool:
        """Check if topic contains version information."""
        if not topic:
            return False
            
        topic_lower = topic.lower()
        return any(keyword in topic_lower for keyword in TopicTypes.VERSION_KEYWORDS)
    
    @classmethod
    def is_location_category(cls, topic: str) -> bool:
        """Check if topic belongs to location category using existing metrics."""
        if not topic:
            return False
            
        # Use existing location metrics definitions
        topic_parts = topic.split('/')
        metric_path = ".".join(topic_parts[-3:]) if len(topic_parts) >= 3 else topic
        
        # Check against known location metrics
        return (metric_path in LOCATION_METRICS or 
                cls.is_coordinate_topic(topic) or 
                cls.is_gps_quality_topic(topic))
    
    @classmethod
    def extract_base_metric(cls, topic: str) -> str:
        """Extract the core metric path from a topic, removing MQTT prefixes."""
        if not topic:
            return ""
            
        parts = topic.split('/')
        
        # Remove common MQTT prefixes and vehicle IDs
        filtered_parts = []
        skip_next = False
        
        for i, part in enumerate(parts):
            if skip_next:
                skip_next = False
                continue
                
            # Skip MQTT structure prefixes
            if part.lower() in ['ovms', 'client', 'metric', 'status']:
                continue
                
            # Skip what looks like usernames/vehicle IDs (between ovms and actual metric)
            if i > 0 and i < len(parts) - 2:
                # This could be username or vehicle ID - keep the core metric parts
                if '.' in part or part.startswith('v.') or part.startswith('m.'):
                    filtered_parts.append(part)
            else:
                filtered_parts.append(part)
        
        return ".".join(filtered_parts[-3:]) if len(filtered_parts) >= 3 else ".".join(filtered_parts)
