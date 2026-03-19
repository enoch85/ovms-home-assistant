"""Naming service for OVMS integration."""

import logging
import re
from typing import Dict, Any, Optional, List

from .const import (
    DOMAIN,
    LOCATION_ENTITY_NAME,
    LOGGER_NAME,
    STATUS_ENTITY_NAME,
    VEHICLE_TOPIC_PREFIXES,
)

_LOGGER = logging.getLogger(LOGGER_NAME)


class EntityNamingService:
    """Service for creating consistent entity names."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize the naming service."""
        self.config = config
        self.vehicle_id = config.get("vehicle_id", "")

    def create_friendly_name(
        self, parts: List[str], metric_info: Optional[Dict], topic: str, raw_name: str
    ) -> str:
        """Create an entity name based on topic parts and metric info."""
        # Handle status topics specially
        if topic and topic.endswith("/status"):
            return STATUS_ENTITY_NAME

        # For vehicle-specific metrics, prioritize the metric name from definitions
        if metric_info and "name" in metric_info:
            base_name = metric_info["name"]

            # Strip any leading vehicle prefix and move it to the end
            for vehicle_label in VEHICLE_TOPIC_PREFIXES.values():
                if base_name.startswith(vehicle_label + " "):
                    base_name = base_name[len(vehicle_label) + 1 :]
                    # If topic ends with a number (like /03), append it
                    if topic and topic.split("/")[-1].isdigit():
                        module_number = topic.split("/")[-1]
                        return f"{base_name} {module_number} ({vehicle_label})"
                    return f"{base_name} ({vehicle_label})"

            # If topic ends with a number (like /03), append it to the name
            if topic and topic.split("/")[-1].isdigit():
                module_number = topic.split("/")[-1]
                return f"{base_name} {module_number}"

            return base_name

        for prefix_key, vehicle_label in VEHICLE_TOPIC_PREFIXES.items():
            has_prefix = (
                any(p == prefix_key for p in parts) if parts else (prefix_key in topic)
            )
            if has_prefix:
                if parts and len(parts) > 0:
                    last_part = parts[-1].replace("_", " ").title()
                    return f"{last_part} ({vehicle_label})"
                return (
                    f"{raw_name.replace('_', ' ').title()} ({vehicle_label})"
                    if raw_name
                    else f"Sensor ({vehicle_label})"
                )

        # Standard handling for other metrics - extract meaningful names from parts
        if parts and len(parts) > 0:
            last_part = parts[-1].replace("_", " ").title()

            return last_part

        # Fallback to cleaned raw name
        return raw_name.replace("_", " ").title() if raw_name else "Unknown"

    def create_device_tracker_name(self) -> str:
        """Create an entity name for the combined device tracker."""
        return LOCATION_ENTITY_NAME

    def extract_vehicle_id_from_device_info(self, device_info: Dict) -> Optional[str]:
        """Extract vehicle ID from device info."""
        try:
            if isinstance(device_info, dict) and "identifiers" in device_info:
                for identifier in device_info["identifiers"]:
                    if (
                        isinstance(identifier, tuple)
                        and len(identifier) > 1
                        and identifier[0] == DOMAIN
                    ):
                        return identifier[1]
        except Exception as ex:
            _LOGGER.exception("Error extracting vehicle ID from device info: %s", ex)
        return None

    def extract_vehicle_id_from_name(self, name: str) -> Optional[str]:
        """Extract vehicle ID from entity name."""
        try:
            match = re.search(r"ovms_([a-zA-Z0-9]+)_", name)
            if match:
                return match.group(1)
        except Exception as ex:
            _LOGGER.exception("Error extracting vehicle ID from name: %s", ex)
        return None
