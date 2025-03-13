"""Topic parser for OVMS MQTT messages."""
import logging
import re
from typing import Dict, Any, Optional, Tuple, List

from ..const import LOGGER_NAME
from ..metrics import (
    BINARY_METRICS,
    get_metric_by_path,
    get_metric_by_pattern,
    determine_category_from_topic,
    create_friendly_name,
)

_LOGGER = logging.getLogger(LOGGER_NAME)

class TopicParser:
    """Parser for OVMS MQTT topics."""

    def __init__(self, config: Dict[str, Any], entity_registry):
        """Initialize the topic parser."""
        self.config = config
        self.entity_registry = entity_registry
        self.structure_prefix = self._format_structure_prefix()

    def _format_structure_prefix(self) -> str:
        """Format the topic structure prefix based on configuration."""
        try:
            structure = self.config.get("topic_structure", "{prefix}/{mqtt_username}/{vehicle_id}")
            prefix = self.config.get("topic_prefix", "ovms")
            vehicle_id = self.config.get("vehicle_id", "")
            mqtt_username = self.config.get("mqtt_username", "")

            # Replace the variables in the structure
            structure_prefix = structure.format(
                prefix=prefix,
                vehicle_id=vehicle_id,
                mqtt_username=mqtt_username,
            )

            return structure_prefix
        except Exception as ex:
            _LOGGER.exception("Error formatting structure prefix: %s", ex)
            # Fallback to a simple default
            prefix = self.config.get("topic_prefix", "ovms")
            vehicle_id = self.config.get("vehicle_id", "")
            return f"{prefix}/{vehicle_id}"

    def parse_topic(self, topic: str, payload: str) -> Optional[Dict[str, Any]]:
        """Parse a topic to determine the entity type and info."""
        try:
            _LOGGER.debug("Parsing topic: %s", topic)

            # Special handling for status topic (module online status)
            if topic.endswith("/status"):
                vehicle_id = self.config.get("vehicle_id", "")
                attributes = {"topic": topic, "category": "diagnostic"}
                # Ensure proper friendly name for status sensor (fixing issue #1)
                friendly_name = f"{vehicle_id} Connection"
                return {
                    "entity_type": "binary_sensor",
                    "name": f"ovms_{vehicle_id}_status",
                    "friendly_name": friendly_name,
                    "attributes": attributes,
                }

            # Skip event topics - we don't need entities for these
            if topic.endswith("/event"):
                return None

            # Check if topic matches our structure prefix
            if not topic.startswith(self.structure_prefix):
                # Alternative check for different username pattern but same vehicle ID
                vehicle_id = self.config.get("vehicle_id", "")
                prefix = self.config.get("topic_prefix", "")
                if (
                    vehicle_id
                    and prefix
                    and f"/{vehicle_id}/" in topic
                    and topic.startswith(prefix)
                ):
                    # Extract parts after vehicle ID
                    parts = topic.split(f"/{vehicle_id}/", 1)
                    if len(parts) > 1:
                        topic_suffix = parts[1]
                    else:
                        return None
                else:
                    return None
            else:
                # Extract the normal way
                topic_suffix = topic[len(self.structure_prefix):].lstrip("/")

            if not topic_suffix:
                return None

            # Split the remaining path into parts
            parts = topic_suffix.split("/")
            parts = [p for p in parts if p]

            if len(parts) < 2:
                return None

            # Check if this is a command/response topic - don't create entities for these
            if (
                "client/rr/command" in topic_suffix
                or "client/rr/response" in topic_suffix
            ):
                return None

            # Handle vendor-specific prefixes (like xvu)
            if len(parts) >= 2 and parts[0] == "metric":
                if parts[1] == "xvu":
                    # This is a vendor-specific metric, adjust parts to match standard pattern
                    if len(parts) > 3:
                        # Create a modified path that might match standard metrics
                        standard_parts = ["metric", parts[2]] + parts[3:]
                        metric_path = ".".join(standard_parts[1:])
                    else:
                        metric_path = ".".join(parts[1:])
                else:
                    metric_path = ".".join(parts[1:])
            else:
                metric_path = ".".join(parts)

            # Try to match with known metric patterns
            # First, check if this is a standard OVMS metric
            metric_info = get_metric_by_path(metric_path)

            # If no exact match, try to match by patterns
            if not metric_info and parts:
                metric_info = get_metric_by_pattern(parts)

            # Determine entity type and category
            entity_type = self._determine_entity_type(parts, metric_path, metric_info)
            category = determine_category_from_topic(parts)

            # Create entity name and add extra attributes
            raw_name = "_".join(parts) if parts else "unknown"
            
            # Get vehicle ID for entity naming
            vehicle_id = self.config.get("vehicle_id", "")
            
            # Include vehicle_id in entity name
            name = f"ovms_{vehicle_id}_{raw_name}"
            
            # Create more descriptive friendly name using the improved function
            friendly_name = self._create_friendly_name(parts, metric_info, topic, raw_name)
                
            attributes = self._prepare_attributes(topic, category, parts, metric_info)

            # Special handling for latitude/longitude
            if self._is_location_topic(parts, name, topic):
                # Give it higher priority as this is for the device tracker
                location_data = {
                    "entity_type": "device_tracker",
                    "name": name,
                    "friendly_name": friendly_name,
                    "attributes": attributes,
                    "priority": 10,  # Higher priority for location data
                }
                
                # Look for GPS signal quality if this is a location topic
                gps_sq = self._find_gps_signal_quality(topic)
                if gps_sq is not None:
                    attributes["gps_accuracy"] = gps_sq
                
                return location_data

            return {
                "entity_type": entity_type,
                "name": name,
                "friendly_name": friendly_name,
                "attributes": attributes,
                "priority": 5 if "version" in name.lower() else 0,  # Higher priority for version
            }

        except Exception as ex:
            _LOGGER.exception("Error parsing topic: %s", ex)
            return None

    def _create_friendly_name(self, parts, metric_info, topic, raw_name):
        """Create a friendly name based on topic parts and metric info."""
        # Extract base metric name from metric info
        if metric_info and "name" in metric_info:
            base_name = metric_info["name"]
        else:
            base_name = parts[-1].replace("_", " ").title() if parts else "Unknown"
        
        # Check for vehicle-specific metrics
        car_prefix = None
        
        # Detect car model from parts or topic
        if "xvu" in topic or "xvu" in raw_name:
            car_prefix = "VW eUP"
        elif "eu3" in topic or "e.up3" in raw_name:
            car_prefix = "VW e-Up3"
        elif "id3" in topic or "id.3" in raw_name:
            car_prefix = "VW ID.3"
        elif "id4" in topic or "id.4" in raw_name:
            car_prefix = "VW ID.4"
        
        # Check if the car prefix is already in the base name
        if car_prefix and car_prefix in base_name:
            return base_name
        
        # If we have a car prefix, add it to the friendly name
        if car_prefix:
            return f"{car_prefix} {base_name}"
        
        # For standard metrics, just use the base name
        return base_name

    def _find_gps_signal_quality(self, topic: str) -> Optional[float]:
        """Find GPS signal quality value for location accuracy."""
        # This is a placeholder - in a real implementation, you would need access to the
        # discovered topics and their values to look up GPS signal quality
        return None

    def _is_location_topic(self, parts: List[str], name: str, topic: str) -> bool:
        """Check if topic is a location topic."""
        location_keywords = ["latitude", "longitude", "lat", "lon", "lng", "gps"]

        # Check in name
        if any(keyword in name.lower() for keyword in location_keywords):
            return True

        # Check in topic
        if any(keyword in topic.lower() for keyword in location_keywords):
            return True

        # Check in parts
        if any(keyword in part.lower() for part in parts for keyword in location_keywords):
            return True

        return False

    def _determine_entity_type(self, parts: List[str], metric_path: str, metric_info: Optional[Dict]) -> str:
        """Determine the entity type based on topic parts and metric info."""
        # Check if this should be a binary sensor
        if self._should_be_binary_sensor(parts, metric_path, metric_info):
            return "binary_sensor"

        # Check for commands/switches
        if "command" in parts or any(
            switch_pattern in "_".join(parts).lower()
            for switch_pattern in [
                "switch",
                "toggle",
                "set",
                "enable",
                "disable",
            ]
        ):
            return "switch"

        # Default to sensor
        return "sensor"

    def _should_be_binary_sensor(self, parts: List[str], metric_path: str, metric_info: Optional[Dict]) -> bool:
        """Determine if topic should be a binary sensor."""
        try:
            # Check if this is a known binary metric
            if metric_path in BINARY_METRICS:
                return True

            # Check if the metric info defines it as a binary sensor
            if metric_info and "device_class" in metric_info:
                # Check if the device class is from binary_sensor
                if hasattr(metric_info["device_class"], "__module__"):
                    return "binary_sensor" in metric_info["device_class"].__module__

            # Check for binary patterns in name
            name_lower = "_".join(parts).lower()
            binary_keywords = [
                "active",
                "enabled",
                "running",
                "connected",
                "locked",
                "door",
                "charging",
            ]

            # Special handling for "on" to avoid false matches
            has_on_word = bool(re.search(r"\bon\b", name_lower))

            # Check for any other binary keywords
            has_binary_keyword = any(
                keyword in name_lower for keyword in binary_keywords
            )

            if has_on_word or has_binary_keyword:
                # Exclude certain words that might contain binary keywords but are numeric
                exclusions = [
                    "power",
                    "energy",
                    "duration",
                    "consumption",
                    "acceleration",
                    "direction",
                    "monotonic",
                ]
                # Check if name contains any exclusions
                if not any(
                    exclusion in name_lower for exclusion in exclusions
                ):
                    return True

            return False
        except Exception as ex:
            _LOGGER.exception(
                "Error determining if should be binary sensor: %s", ex
            )
            return False

    def _prepare_attributes(self, topic: str, category: str, parts: List[str], metric_info: Optional[Dict]) -> Dict[str, Any]:
        """Prepare entity attributes."""
        try:
            attributes = {
                "topic": topic,
                "category": category,
                "parts": parts,
            }

            # Add additional attributes from metric definition
            if metric_info:
                # Only add attributes that aren't already in the entity definition
                for key, value in metric_info.items():
                    if key not in [
                        "name",
                        "device_class",
                        "state_class",
                        "unit",
                    ]:
                        attributes[key] = value

            return attributes
        except Exception as ex:
            _LOGGER.exception("Error preparing attributes: %s", ex)
            return {"topic": topic, "category": category}
