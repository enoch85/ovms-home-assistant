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

    def create_friendly_name(
        self, parts: List[str], metric_info: Optional[Dict], topic: str, raw_name: str
    ) -> str:
        """Create a friendly name based on topic parts and metric info."""
        # Handle status topics specially
        if topic and topic.endswith("/status"):
            return f"{self.vehicle_id} Status"

        # For vehicle-specific metrics (like xvu/VW eUP!), prioritize the metric name exactly as defined
        # This preserves names like "VW eUP! Absolute Battery Capacity" without modification
        if metric_info and "name" in metric_info:
            base_name = metric_info["name"]

            # If topic ends with a number (like /03), append it to the name
            if topic and topic.split("/")[-1].isdigit():
                module_number = topic.split("/")[-1]
                return f"{base_name} {module_number}"

            return base_name

        # Check if this is a VW eUP! metric by looking for 'xvu' prefix
        has_xvu = any(p == "xvu" for p in parts) if parts else ("xvu" in topic)
        if has_xvu:
            if parts and len(parts) > 0:
                last_part = parts[-1].replace("_", " ").title()
                return f"VW eUP! {last_part}"
            return (
                f"VW eUP! {raw_name.replace('_', ' ').title()}"
                if raw_name
                else "VW eUP! Sensor"
            )

        # Check if this is a Smart ForTwo metric by looking for 'xsq' prefix
        has_xsq = any(p == "xsq" for p in parts) if parts else ("xsq" in topic)
        if has_xsq:
            if parts and len(parts) > 0:
                last_part = parts[-1].replace("_", " ").title()
                return f"Smart ForTwo {last_part}"
            return (
                f"Smart ForTwo {raw_name.replace('_', ' ').title()}"
                if raw_name
                else "Smart ForTwo Sensor"
            )

        # Check if this is an MG ZS-EV metric by looking for 'xmg' prefix
        has_xmg = any(p == "xmg" for p in parts) if parts else ("xmg" in topic)
        if has_xmg:
            if parts and len(parts) > 0:
                last_part = parts[-1].replace("_", " ").title()
                return f"MG ZS-EV {last_part}"
            return (
                f"MG ZS-EV {raw_name.replace('_', ' ').title()}"
                if raw_name
                else "MG ZS-EV Sensor"
            )

        # Check if this is a Nissan Leaf metric by looking for 'xnl' prefix
        has_xnl = any(p == "xnl" for p in parts) if parts else ("xnl" in topic)
        if has_xnl:
            if parts and len(parts) > 0:
                last_part = parts[-1].replace("_", " ").title()
                return f"Nissan Leaf {last_part}"
            return (
                f"Nissan Leaf {raw_name.replace('_', ' ').title()}"
                if raw_name
                else "Nissan Leaf Sensor"
            )

        # Check if this is a Renault Twizy metric by looking for 'xrt' prefix
        has_xrt = any(p == "xrt" for p in parts) if parts else ("xrt" in topic)
        if has_xrt:
            if parts and len(parts) > 0:
                last_part = parts[-1].replace("_", " ").title()
                return f"Renault Twizy {last_part}"
            return (
                f"Renault Twizy {raw_name.replace('_', ' ').title()}"
                if raw_name
                else "Renault Twizy Sensor"
            )

        # Standard handling for other metrics - extract meaningful names from parts
        if parts and len(parts) > 0:
            last_part = parts[-1].replace("_", " ").title()

            return last_part

        # Fallback to cleaned raw name
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
