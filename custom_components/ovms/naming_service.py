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
        # For vehicle-specific metrics (like xvu/VW eUP!), prioritize the metric name exactly as defined
        # This preserves names like "VW eUP! Absolute Battery Capacity" without modification
        if metric_info and "name" in metric_info:
            # Vehicle-specific metrics already have the vehicle name in the metric definition
            return metric_info["name"]

        # If no metric info, try to extract a clean name from parts
        if parts:
            last_part = parts[-1].replace("_", " ").title()
            return last_part

        # Fallback to a cleaned version of the raw name
        return raw_name.replace("_", " ").title() if raw_name else "Unknown"

    def create_device_tracker_name(self, vehicle_id: Optional[str] = None) -> str:
        """Create a friendly name for device tracker."""
        if not vehicle_id:
            vehicle_id = self.vehicle_id
        return f"{vehicle_id} Location"

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
