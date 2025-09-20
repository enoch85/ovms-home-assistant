"""Topic parser for OVMS MQTT messages."""
import logging
import re
from typing import Dict, Any, Optional, Tuple, List

from .. import metrics
from ..const import LOGGER_NAME, CONF_TOPIC_BLACKLIST, SYSTEM_TOPIC_BLACKLIST, SYSTEM_SWITCH_BLACKLIST, DEFAULT_USER_TOPIC_BLACKLIST
from ..metrics import (
    BINARY_METRICS,
    get_metric_by_path,
    get_metric_by_pattern,
)

_LOGGER = logging.getLogger(LOGGER_NAME)

class TopicParser:
    """Parser for OVMS MQTT topics."""

    def __init__(self, config: Dict[str, Any], entity_registry):
        """Initialize the topic parser."""
        self.config = config
        self.entity_registry = entity_registry
        self.structure_prefix = self._format_structure_prefix()
        self.coordinate_entities_created = {}  # Track which coordinate entities we've created

        # Get and normalize the topic blacklist - combine system and user patterns
        user_blacklist = config.get(CONF_TOPIC_BLACKLIST, DEFAULT_USER_TOPIC_BLACKLIST)
        combined_blacklist = SYSTEM_TOPIC_BLACKLIST + user_blacklist
        self.topic_blacklist = self._normalize_blacklist(combined_blacklist)

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
                # Ensure proper friendly name for status sensor
                friendly_name = f"{vehicle_id} Status"
                return {
                    "entity_type": "binary_sensor",
                    "name": f"ovms_{vehicle_id}_status",
                    "friendly_name": friendly_name,
                    "attributes": attributes,
                }

            # Skip event topics - we don't need entities for these
            if topic.endswith("/event"):
                return None

            # Skip blacklisted topics
            if self.topic_blacklist:
                for pattern in self.topic_blacklist:
                    if pattern in topic:
                        _LOGGER.debug("Skipping blacklisted topic pattern '%s': %s", pattern, topic)
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

            # Log the topic and the derived parts only during initial setup
            # This prevents the "logging too frequently" warning
            if len(parts) < 5:  # Only log for shorter, likely important paths
                _LOGGER.debug(f"Pre-categorization: Topic='{topic}', Suffix='{topic_suffix}', Derived Parts='{parts}'")

            if len(parts) < 2:
                return None

            # Check if this is a command/response topic - don't create entities for these
            if (
                "client/rr/command" in topic_suffix
                or "client/rr/response" in topic_suffix
            ):
                return None

            # Handle vendor-specific prefixes (like xvu, xsq, xmg, xnl)
            metric_path = self._convert_to_metric_path(parts)

            # Determine entity type and category
            entity_type = self._determine_entity_type(parts, metric_path, topic)
            # Use centralized category determination from metrics module
            category = metrics.determine_category_from_topic(parts)

            # Additional logging for GPS location topics
            if any(keyword in topic.lower() for keyword in ["latitude", "longitude", "gps"]) or (len(parts) >= 2 and parts[0] == "v" and parts[1] == "p"):
                _LOGGER.info(f"GPS Location Topic Processing - Topic: {topic}, Parts: {parts}, Category: {category}")

            # Create entity name and add extra attributes
            raw_name = "_".join(parts) if parts else "unknown"
            vehicle_id = self.config.get("vehicle_id", "")
            name = f"ovms_{vehicle_id}_{raw_name}"

            # Get metric info for later use
            metric_info = get_metric_by_path(metric_path)
            if not metric_info:
                metric_info = get_metric_by_pattern(parts)

            # Prepare basic attributes
            attributes = {
                "topic": topic,
                "category": category,
                "parts": parts,
            }

            return {
                "entity_type": entity_type,
                "name": name,
                "raw_name": raw_name,
                "parts": parts,
                "metric_path": metric_path,
                "metric_info": metric_info,
                "attributes": attributes,
                "priority": 5 if "version" in name.lower() else 0,
            }

        except Exception as ex:
            _LOGGER.exception("Error parsing topic: %s", ex)
            return None

    def _convert_to_metric_path(self, parts: List[str]) -> str:
        """Convert topic parts to metric path."""
        # Keep vendor-specific prefixes intact
        if len(parts) >= 2:
            # VW e-UP metrics
            if "xvu" in parts:
                return ".".join(parts)

            # Smart ForTwo metrics
            if "xsq" in parts:
                return ".".join(parts)

            # MG ZS-EV metrics
            if "xmg" in parts:
                return ".".join(parts)

            # Nissan Leaf metrics
            if "xnl" in parts:
                return ".".join(parts)

            # Renault Twizy metrics
            if "xrt" in parts:
                return ".".join(parts)

            # Metric specific prefixes
            if parts[0] in ["metric", "status", "notify"]:
                return ".".join(parts[1:])

        return ".".join(parts)

    def _determine_entity_type(self, parts: List[str], metric_path: str, topic: str) -> str:
        """Determine the entity type based on topic parts and metric info."""
        # Check if this should be a binary sensor
        if self._should_be_binary_sensor(parts, metric_path):
            return "binary_sensor"

        # Check for commands/switches (v.e.cabinsetpoint is not a switch)
        if metric_path not in SYSTEM_SWITCH_BLACKLIST and (
            "command" in parts or any(            
            switch_pattern in "_".join(parts).lower()
                for switch_pattern in [
                    "switch",
                    "toggle",
                    "set",
                    "enable",
                    "disable",
                ]
            )
        ):
            return "switch"

        # GPS metrics should be sensors
        if self._is_gps_metric_topic(parts, "_".join(parts), topic):
            return "sensor"

        # Default to sensor
        return "sensor"

    def _should_be_binary_sensor(self, parts: List[str], metric_path: str) -> bool:
        """Determine if topic should be a binary sensor."""
        try:
            # Check if this is a known binary metric
            if metric_path in BINARY_METRICS:
                return True

            # Check if the metric info defines it as a binary sensor
            metric_info = get_metric_by_path(metric_path)
            if not metric_info:
                metric_info = get_metric_by_pattern(parts)

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
                "fan",       # Added for MG ZS-EV radiator fan
                "relay",     # Added for MG ZS-EV relays
                "error",     # Added for MG ZS-EV battery error
                "auth",      # Added for MG ZS-EV auth
                "polling",   # Added for MG ZS-EV polling
                "heat",      # Added for Nissan Leaf remote heat
                "cool",      # Added for Nissan Leaf remote cool
                "granted",   # Added for Nissan Leaf heater granted
                "present",   # Added for Nissan Leaf heater present
                "requested", # Added for Nissan Leaf heat requested
                "progress",  # Added for Nissan Leaf request in progress
                "quick",     # Added for Nissan Leaf quick charge status
                "auto",      # Added for Nissan Leaf auto HVAC
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
                if not any(exclusion in name_lower for exclusion in exclusions):
                    return True

            return False
        except Exception as ex:
            _LOGGER.exception("Error determining if should be binary sensor: %s", ex)
            return False

    def _is_coordinate_topic(self, parts: List[str], name: str, topic: str) -> bool:
        """Check if topic is a latitude/longitude coordinate topic.

        These topics contain actual location coordinates.
        """
        # Define strict coordinate keywords - only these will create device trackers
        coordinate_keywords = ["latitude", "lat", "longitude", "long", "lon", "lng"]

        # Only match exact coordinate keywords, not any topic containing "gps"
        for keyword in coordinate_keywords:
            # Check in topic name
            if keyword == name.lower():
                return True

            # Check for exact match in parts
            if any(part.lower() == keyword for part in parts):
                return True

            # Check in full topic path for exact coordinate matches
            if f"/p/{keyword}" in topic.lower() or f".p.{keyword}" in topic.lower():
                return True

        # For multi-part words like "v_p_latitude", we need additional check
        if any(part.lower().endswith("_latitude") or
               part.lower().endswith("_longitude") for part in parts):
            return True

        return False

    def _is_gps_metric_topic(self, parts: List[str], name: str, topic: str) -> bool:
        """Check if topic is a GPS-related metric that should be a sensor."""
        gps_keywords = ["gpshdop", "gpssq", "gpsmode", "gpsspeed", "gpstime", "gps"]
        coordinate_keywords = ["latitude", "lat", "longitude", "long", "lon", "lng"]

        # GPS topics OR coordinate topics should be sensors
        if (any(keyword in topic.lower() for keyword in gps_keywords) or
            any(keyword in topic.lower() for keyword in coordinate_keywords)):
            return True

        return False

    def _normalize_blacklist(self, blacklist):
        """Normalize the blacklist format to always be a list of patterns."""
        if not blacklist:
            return []

        # If it's already a list, use it directly
        if isinstance(blacklist, list):
            return [str(item) for item in blacklist if item]

        # Convert string to list (handling comma-separated input from UI)
        if isinstance(blacklist, str):
            return [x.strip() for x in blacklist.split(",") if x.strip()]

        # Fallback to system defaults
        return SYSTEM_TOPIC_BLACKLIST
