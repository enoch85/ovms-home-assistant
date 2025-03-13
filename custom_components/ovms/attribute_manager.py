"""Attribute manager for OVMS integration."""
import json
import logging
from typing import Dict, Any, Optional, List

from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util

from .const import LOGGER_NAME
from .metrics import get_metric_by_path, get_metric_by_pattern

_LOGGER = logging.getLogger(LOGGER_NAME)

class AttributeManager:
    """Manager for entity attributes."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize the attribute manager."""
        self.config = config

    def prepare_attributes(self, topic: str, category: str, parts: List[str],
                          metric_info: Optional[Dict] = None) -> Dict[str, Any]:
        """Prepare entity attributes."""
        try:
            attributes = {
                "topic": topic,
                "category": category,
                "parts": parts,
                "last_updated": dt_util.utcnow().isoformat(),
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

    def process_json_payload(self, payload: str, attributes: Dict[str, Any]) -> Dict[str, Any]:
        """Process JSON payload to extract additional attributes."""
        try:
            json_data = json.loads(payload)
            if isinstance(json_data, dict):
                # Add useful attributes from the data
                for key, value in json_data.items():
                    if (key not in ["value", "state", "status"] and
                            key not in attributes):
                        attributes[key] = value

                # If there's a timestamp in the JSON, use it
                if "timestamp" in json_data:
                    attributes["device_timestamp"] = json_data["timestamp"]

            # Update timestamp attribute
            attributes["last_updated"] = dt_util.utcnow().isoformat()

        except (ValueError, json.JSONDecodeError):
            # Not JSON, that's fine
            pass

        return attributes

    def determine_entity_category(self, category: str) -> Optional[EntityCategory]:
        """Determine EntityCategory from attribute category."""
        if category in ["diagnostic", "network", "system"]:
            return EntityCategory.DIAGNOSTIC
        return None

    def get_gps_attributes(self, topic: str, payload: Any) -> Dict[str, Any]:
        """Extract and prepare GPS-related attributes."""
        attributes = {}

        try:
            # Handle GPS-specific attributes
            if "gpshdop" in topic.lower():
                try:
                    value = float(payload) if payload else None
                    attributes["gps_hdop"] = value
                    # If we have HDOP, we can estimate accuracy (meters)
                    if value is not None:
                        # HDOP to meters accuracy - typical formula
                        # Each HDOP unit is roughly 5 meters of accuracy
                        accuracy = max(5, value * 5)  # Minimum 5m
                        attributes["gps_accuracy"] = accuracy
                        attributes["gps_accuracy_unit"] = "m"
                except (ValueError, TypeError):
                    pass
            elif "gpssq" in topic.lower():
                try:
                    value = float(payload) if payload else None
                    attributes["gps_signal_quality"] = value
                    # Update accuracy based on signal quality
                    if value is not None:
                        # Simple formula that translates signal quality to meters accuracy
                        # Higher signal quality = better accuracy (lower value)
                        accuracy = max(5, 100 - value)  # Clamp minimum accuracy to 5m
                        attributes["gps_accuracy"] = accuracy
                        attributes["gps_accuracy_unit"] = "m"
                except (ValueError, TypeError):
                    pass
            elif "gpsspeed" in topic.lower():
                try:
                    value = float(payload) if payload else None
                    attributes["gps_speed"] = value
                except (ValueError, TypeError):
                    pass

        except Exception as ex:
            _LOGGER.exception("Error processing GPS attributes: %s", ex)

        return attributes
