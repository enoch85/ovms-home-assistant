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

    def _vehicle_topic_descriptor(self, parts: Optional[List[str]]) -> Optional[str]:
        """Name a vehicle-specific topic from its segments after the prefix.

        Args:
            parts: Topic segments after the vehicle id

        Returns:
            e.g. "V Charge Bcb Power (Smart ForTwo)" for
            ["metric", "xsq", "v", "charge", "bcb", "power"], or None when the
            topic carries no vehicle prefix or nothing follows it.
        """
        tail: List[str] = []
        vehicle_label = None
        for part in parts or []:
            if vehicle_label is not None:
                tail.append(part)
            else:
                vehicle_label = VEHICLE_TOPIC_PREFIXES.get(part)
        if not tail:
            return None
        descriptor = " ".join(tail).replace("_", " ").title()
        return f"{descriptor} ({vehicle_label})"

    def create_friendly_name(
        self,
        parts: List[str],
        metric_info: Optional[Dict],
        topic: str,
        raw_name: str,
        metric_defined: bool = True,
    ) -> str:
        """Create an entity name based on topic parts and metric info.

        Args:
            parts: Topic segments after the vehicle id
            metric_info: Metric definition or generic topic pattern, if any
            topic: Full MQTT topic
            raw_name: Underscore-joined topic segments
            metric_defined: False when metric_info is only a generic topic
                pattern ("power", "temp", ...) rather than a definition of
                this metric

        Returns:
            The entity name; vehicle-specific metrics end in "(Make Model)".
        """
        # Handle status topics specially
        if topic and topic.endswith("/status"):
            return STATUS_ENTITY_NAME

        # A generic pattern names every topic it matches identically and knows
        # nothing about the vehicle, so an undefined vehicle-specific metric
        # such as xsq.v.charge.bcb.power would read a bare "Power". Describe it
        # by its topic instead, like any other undefined vehicle metric.
        if not metric_defined:
            descriptor = self._vehicle_topic_descriptor(parts)
            if descriptor:
                return descriptor

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

            # A prefix-pattern match (a vehicle-specific topic with no specific
            # metric definition) leaves base_name as just the bare vehicle label,
            # e.g. "VW eUP!". Derive a descriptor from the topic segments after
            # the vehicle prefix so the entity reads "B Soc (VW eUP!)" instead of
            # only "VW eUP!" repeated across every undefined metric.
            if base_name in VEHICLE_TOPIC_PREFIXES.values():
                descriptor = self._vehicle_topic_descriptor(parts)
                if descriptor:
                    return descriptor

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
