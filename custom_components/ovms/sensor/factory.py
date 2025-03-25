"""OVMS sensor factory functions."""
import logging
import hashlib
from typing import Any, Dict, List, Optional

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfPower,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.helpers.entity import EntityCategory

from ..const import LOGGER_NAME
from ..metrics import get_metric_by_path, get_metric_by_pattern
from ..metrics.patterns import TOPIC_PATTERNS

_LOGGER = logging.getLogger(LOGGER_NAME)

def determine_sensor_type(internal_name: str, topic: str, attributes: Dict[str, Any]) -> Dict[str, Any]:
    """Determine the sensor type based on metrics definitions."""
    result = {
        "device_class": None,
        "state_class": None,
        "native_unit_of_measurement": None,
        "entity_category": None,
        "icon": None,
    }

    # Check if attributes specify a category
    if "category" in attributes:
        category = attributes["category"]
        # Apply diagnostic entity category to network and system sensors
        if category in ["diagnostic", "network", "system"]:
            result["entity_category"] = EntityCategory.DIAGNOSTIC
            if category != "diagnostic":  # Don't return for network/system to allow further processing
                _LOGGER.debug(
                    "Setting EntityCategory.DIAGNOSTIC for %s category: %s",
                    category, internal_name
                )

    # Special check for timer mode sensors
    if "timermode" in internal_name.lower() or "timer_mode" in internal_name.lower():
        result["icon"] = "mdi:timer-outline"
        return result

    # Special handling for GPS coordinates
    name_lower = internal_name.lower()
    if "latitude" in name_lower or "lat" in name_lower:
        result["icon"] = "mdi:latitude"
        result["state_class"] = SensorStateClass.MEASUREMENT
        return result
    elif "longitude" in name_lower or "lon" in name_lower or "lng" in name_lower:
        result["icon"] = "mdi:longitude"
        result["state_class"] = SensorStateClass.MEASUREMENT
        return result

    # Extract metric path from topic
    topic_suffix = topic
    if topic.count('/') >= 3:  # Skip the prefix part
        parts = topic.split('/')
        # Find where the actual metric path starts
        for i, part in enumerate(parts):
            if part in ["metric", "status", "notify", "command", "m", "v", "s", "t"]:
                topic_suffix = '/'.join(parts[i:])
                break

    # Create both standard and alternative metric paths for matching
    metric_path = topic_suffix.replace("/", ".")
    alt_metric_path = None

    # Handle "metric/" prefix - remove it for better matching with definitions
    if metric_path.startswith("metric."):
        alt_metric_path = metric_path[7:]  # Remove "metric."

    # Try exact match first
    metric_info = get_metric_by_path(metric_path)

    # If no match and we have an alternative path, try that
    if not metric_info and alt_metric_path:
        metric_info = get_metric_by_path(alt_metric_path)

    # If no exact match, try by pattern in name and topic
    if not metric_info:
        topic_parts = topic_suffix.split('/')
        name_parts = internal_name.split('_')
        metric_info = get_metric_by_pattern(topic_parts) or get_metric_by_pattern(name_parts)

    # Apply metric info if found
    if metric_info:
        if "device_class" in metric_info:
            result["device_class"] = metric_info["device_class"]
        if "state_class" in metric_info:
            result["state_class"] = metric_info["state_class"]
        if "unit" in metric_info:
            result["native_unit_of_measurement"] = metric_info["unit"]
        if "entity_category" in metric_info:
            result["entity_category"] = metric_info["entity_category"]
        if "icon" in metric_info:
            result["icon"] = metric_info["icon"]
        return result

    # If no metric info found, try matching by pattern from TOPIC_PATTERNS
    for pattern, pattern_info in TOPIC_PATTERNS.items():
        if pattern in internal_name.lower() or pattern in topic.lower():
            if "device_class" in pattern_info:
                result["device_class"] = pattern_info["device_class"]
            if "state_class" in pattern_info:
                result["state_class"] = pattern_info["state_class"]
            if "unit" in pattern_info:
                result["native_unit_of_measurement"] = pattern_info["unit"]
            if "entity_category" in pattern_info:
                result["entity_category"] = pattern_info["entity_category"]
            if "icon" in pattern_info:
                result["icon"] = pattern_info["icon"]
            break

    return result

def add_device_specific_attributes(attributes: Dict[str, Any], device_class: Any, native_value: Any) -> Dict[str, Any]:
    """Add attributes based on device class and value."""
    updated_attrs = attributes.copy()

    # Add derived attributes based on entity type
    if device_class is not None:
        # Add specific attributes for different device classes
        if device_class == SensorDeviceClass.BATTERY:
            # Add battery-specific attributes
            if native_value is not None:
                try:
                    value = float(native_value)
                    if value <= 20:
                        updated_attrs["battery_level"] = "low"
                    elif value <= 50:
                        updated_attrs["battery_level"] = "medium"
                    else:
                        updated_attrs["battery_level"] = "high"
                except (ValueError, TypeError):
                    pass

        elif device_class == SensorDeviceClass.TEMPERATURE:
            # Add temperature-specific attributes
            if native_value is not None:
                try:
                    temp = float(native_value)
                    if "ambient" in updated_attrs.get("category", "").lower() or "cabin" in updated_attrs.get("category", "").lower():
                        if temp < 0:
                            updated_attrs["temperature_level"] = "freezing"
                        elif temp < 10:
                            updated_attrs["temperature_level"] = "cold"
                        elif temp < 20:
                            updated_attrs["temperature_level"] = "cool"
                        elif temp < 25:
                            updated_attrs["temperature_level"] = "comfortable"
                        elif temp < 30:
                            updated_attrs["temperature_level"] = "warm"
                        else:
                            updated_attrs["temperature_level"] = "hot"
                except (ValueError, TypeError):
                    pass

    return updated_attrs

def create_cell_sensors(topic: str, cell_values: List[float],
                        vehicle_id: str, parent_unique_id: str,
                        device_info: Dict[str, Any], attributes: Dict[str, Any],
                        create_individual_sensors: bool = False) -> List[Dict[str, Any]]:
    """Create configuration for individual cell sensors.

    Args:
        create_individual_sensors: If True, create individual sensors for cells.
                                 If False, only add as attributes (original behavior).
    """
    # NEVER create individual cell sensors by default
    # This maintains the original behavior where cell values are only attributes
    # Must be explicitly enabled via configuration
    if not create_individual_sensors:
        return []

    # Add topic hash to make unique IDs truly unique
    topic_hash = hashlib.md5(topic.encode()).hexdigest()[:8]
    category = attributes.get("category", "battery")

    # Parse topic to extract just the metric path
    topic_suffix = topic
    if topic.count('/') >= 3:
        parts = topic.split('/')
        for i, part in enumerate(parts):
            if part in ["metric", "status", "notify", "command", "m", "v", "s", "t"]:
                topic_suffix = '/'.join(parts[i:])
                break

    # Convert to metric path
    topic_parts = topic_suffix.split('/')
    metric_path = "_".join(topic_parts)

    # Determine the appropriate attribute name type based on sensor context
    stat_type = "cell"  # Default fallback
    sensor_name = attributes.get("name", "").lower()
    if "temp" in sensor_name:
        stat_type = "temp"
    elif "voltage" in sensor_name:
        stat_type = "voltage"

    sensor_configs = []

    # Create sensors
    for i, value in enumerate(cell_values):
        # Generate unique entity name that includes the parent metric path
        entity_name = f"ovms_{vehicle_id}_{category}_{metric_path}_{stat_type}_{i+1}".lower()

        # Generate unique ID using hash
        cell_unique_id = f"{vehicle_id}_{category}_{topic_hash}_{stat_type}_{i+1}"

        # Create friendly name for cell
        friendly_name = f"{attributes.get('name', stat_type.capitalize())} {stat_type.capitalize()} {i+1}"

        # Create sensor config
        sensor_config = {
            "unique_id": cell_unique_id,
            "name": entity_name,
            "friendly_name": friendly_name,
            "state": value,
            "device_info": device_info,
            "topic": f"{topic}/{stat_type}/{i+1}",
            "attributes": {
                "cell_index": i,
                "parent_unique_id": parent_unique_id,
                "parent_topic": topic,
                "category": category,
                "device_class": attributes.get("device_class"),
                "state_class": SensorStateClass.MEASUREMENT,
                "unit_of_measurement": attributes.get("unit_of_measurement"),
            },
        }

        sensor_configs.append(sensor_config)

    return sensor_configs
