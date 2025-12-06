"""Attribute manager for OVMS integration."""

import json
import logging
from typing import Dict, Any, Optional, List

from homeassistant.const import EntityCategory
from homeassistant.util import dt as dt_util

from .const import (
    LOGGER_NAME,
    GPS_ACCURACY_MIN_METERS,
    GPS_ACCURACY_MAX_METERS,
    GPS_HDOP_METERS_MULTIPLIER,
)
from .metrics import get_metric_by_path, get_metric_by_pattern

_LOGGER = logging.getLogger(LOGGER_NAME)


class AttributeManager:
    """Manager for entity attributes."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize the attribute manager."""
        self.config = config

    def prepare_attributes(
        self,
        topic: str,
        category: str,
        parts: List[str],
        metric_info: Optional[Dict] = None,
    ) -> Dict[str, Any]:
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

    def process_json_payload(
        self, payload: str, attributes: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process JSON payload to extract additional attributes."""
        try:
            json_data = json.loads(payload)
            if isinstance(json_data, dict):
                # Add useful attributes from the data
                for key, value in json_data.items():
                    if (
                        key not in ["value", "state", "status"]
                        and key not in attributes
                    ):
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
        """Extract and prepare GPS-related attributes.

        Handles GPS quality metrics and calculates accuracy in meters.
        Supports both v.p.gpssq (signal quality 0-100%) and v.p.gpshdop (HDOP).

        Args:
            topic: The MQTT topic containing the GPS data
            payload: The payload value from the topic

        Returns:
            Dictionary of GPS-related attributes including accuracy when calculable
        """
        attributes = {}

        try:
            # Handle HDOP (Horizontal Dilution of Precision)
            if "gpshdop" in topic.lower():
                try:
                    value = float(payload) if payload else None
                    attributes["gps_hdop"] = value
                    # HDOP to meters accuracy - each unit is ~5 meters
                    if value is not None:
                        accuracy = max(
                            GPS_ACCURACY_MIN_METERS,
                            value * GPS_HDOP_METERS_MULTIPLIER,
                        )
                        attributes["gps_accuracy"] = accuracy
                        attributes["gps_accuracy_unit"] = "m"
                except (ValueError, TypeError):
                    pass

            # Handle GPS Signal Quality (v.p.gpssq - OVMS 3.3.005+)
            # 0-100% where <30 unusable, >50 good, >80 excellent
            elif "gpssq" in topic.lower():
                try:
                    value = float(payload) if payload else None
                    attributes["gps_signal_quality"] = value
                    # Signal quality 0-100% maps inversely to accuracy in meters
                    if value is not None:
                        accuracy = max(
                            GPS_ACCURACY_MIN_METERS,
                            GPS_ACCURACY_MAX_METERS - value,
                        )
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
