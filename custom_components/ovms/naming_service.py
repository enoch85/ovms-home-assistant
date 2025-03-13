"""Naming service for OVMS integration."""
import logging
import re
from typing import Dict, Any, Optional, List

from .const import LOGGER_NAME, DOMAIN

_LOGGER = logging.getLogger(LOGGER_NAME)

class EntityNamingService:
    """Service for creating consistent entity names."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize the naming service."""
        self.config = config
        self.vehicle_id = config.get("vehicle_id", "")

    def create_friendly_name(self, parts: List[str], metric_info: Optional[Dict],
                            topic: str, raw_name: str) -> str:
        """Create a friendly name based on topic parts and metric info."""
        # Extract base metric name from metric info
        if metric_info and "name" in metric_info:
            base_name = metric_info["name"]
        else:
            base_name = parts[-1].replace("_", " ").title() if parts else "Unknown"

        # Detect car model from parts or topic
        car_prefix = self._detect_car_model(topic, raw_name)

        # Special handling for battery capacity sensors
        if "b_cap" in topic:
            if "ah_norm" in topic:
                return self.create_battery_capacity_name(car_prefix, "Ah Normalized")
            elif "kwh_abs" in topic:
                return self.create_battery_capacity_name(car_prefix, "kWh Absolute")

        # Check if the car prefix is already in the base name
        if car_prefix and car_prefix in base_name:
            return base_name

        # For all sensors, include vehicle prefix if not already included
        if car_prefix:
            return f"{car_prefix} {base_name}"

        # For standard metrics, just use the base name
        return base_name

    def create_device_tracker_name(self, vehicle_id: Optional[str] = None) -> str:
        """Create a friendly name for device tracker."""
        if not vehicle_id:
            vehicle_id = self.vehicle_id
        return f"({vehicle_id}) Location"

    def create_battery_capacity_name(self, vehicle_name: str, type_suffix: str) -> str:
        """Create a friendly name for battery capacity sensors."""
        return f"{vehicle_name} Battery Capacity ({type_suffix})"

    def _detect_car_model(self, topic: str, raw_name: str) -> Optional[str]:
        """Detect car model from topic or name."""
        if "xvu" in topic or "xvu" in raw_name:
            return "VW eUP"
        elif "eu3" in topic or "e.up3" in raw_name:
            return "VW e-Up3"
        elif "id3" in topic or "id.3" in raw_name:
            return "VW ID.3"
        elif "id4" in topic or "id.4" in raw_name:
            return "VW ID.4"
        elif self.vehicle_id:
            return self.vehicle_id  # Use vehicle_id as prefix if no specific model detected
        return None

    def extract_vehicle_id_from_device_info(self, device_info: Dict) -> Optional[str]:
        """Extract vehicle ID from device info."""
        try:
            if isinstance(device_info, dict) and "identifiers" in device_info:
                for identifier in device_info["identifiers"]:
                    if isinstance(identifier, tuple) and len(identifier) > 1 and identifier[0] == DOMAIN:
                        return identifier[1]
        except Exception as ex:
            _LOGGER.exception("Error extracting vehicle ID from device info: %s", ex)
        return None

    def extract_vehicle_id_from_name(self, name: str) -> Optional[str]:
        """Extract vehicle ID from entity name."""
        try:
            match = re.search(r'ovms_([a-zA-Z0-9]+)_', name)
            if match:
                return match.group(1)
        except Exception as ex:
            _LOGGER.exception("Error extracting vehicle ID from name: %s", ex)
        return None
