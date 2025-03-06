"""Metrics definitions for OVMS integration.

This module provides access to all metric definitions used to interpret OVMS data.
Metrics are organized by category (battery, climate, etc.) for better maintainability.
"""
import logging
from typing import Dict, List, Optional, Any, Union

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfPower,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.helpers.entity import EntityCategory

# Import all metric categories
from .battery import BATTERY_METRICS
from .climate import CLIMATE_METRICS
from .door import DOOR_METRICS
from .location import LOCATION_METRICS
from .motor import MOTOR_METRICS
from .network import NETWORK_METRICS
from .power import POWER_METRICS
from .system import SYSTEM_METRICS
from .tire import TIRE_METRICS
from .vehicle import VEHICLE_METRICS
from .patterns import TOPIC_PATTERNS

# Categories of metrics
CATEGORY_BATTERY = "battery"
CATEGORY_CHARGING = "charging"
CATEGORY_CLIMATE = "climate"
CATEGORY_DOOR = "door"
CATEGORY_LOCATION = "location"
CATEGORY_MOTOR = "motor"
CATEGORY_TRIP = "trip"
CATEGORY_DEVICE = "device"
CATEGORY_DIAGNOSTIC = "diagnostic"
CATEGORY_POWER = "power"
CATEGORY_NETWORK = "network"
CATEGORY_SYSTEM = "system"
CATEGORY_TIRE = "tire"

# Custom unit constants
UNIT_AMPERE_HOUR = "Ah"

# Combine all metrics into a single dictionary
METRIC_DEFINITIONS = {
    **BATTERY_METRICS,
    **CLIMATE_METRICS,
    **DOOR_METRICS,
    **LOCATION_METRICS,
    **MOTOR_METRICS,
    **NETWORK_METRICS,
    **POWER_METRICS,
    **SYSTEM_METRICS,
    **TIRE_METRICS,
    **VEHICLE_METRICS,
}

# Binary metrics that should be boolean
BINARY_METRICS = [
    k for k, v in METRIC_DEFINITIONS.items() 
    if v.get("device_class") in [
        BinarySensorDeviceClass.DOOR,
        BinarySensorDeviceClass.LOCK,
        BinarySensorDeviceClass.BATTERY_CHARGING,
        BinarySensorDeviceClass.CONNECTIVITY,
        BinarySensorDeviceClass.POWER,
        BinarySensorDeviceClass.PROBLEM,
        BinarySensorDeviceClass.RUNNING,
    ] or k.endswith(('.on', '.charging', '.alarm', '.alert', '.locked', '.hvac'))
]

# Prefix patterns to detect entity categories
PREFIX_CATEGORIES = {
    "v.b": CATEGORY_BATTERY,
    "v.c": CATEGORY_CHARGING,
    "v.d": CATEGORY_DOOR,
    "v.e.cabin": CATEGORY_CLIMATE,
    "v.e": CATEGORY_DIAGNOSTIC,
    "v.g": CATEGORY_POWER,
    "v.i": CATEGORY_MOTOR,
    "v.m": CATEGORY_MOTOR,
    "v.p": CATEGORY_LOCATION,
    "v.t": CATEGORY_TIRE,
    "m.net": CATEGORY_NETWORK,
    "m": CATEGORY_SYSTEM,
    "s": CATEGORY_SYSTEM,
}

# Group metrics by categories
METRIC_CATEGORIES = {
    CATEGORY_BATTERY: [k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_BATTERY],
    CATEGORY_CHARGING: [k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_CHARGING],
    CATEGORY_CLIMATE: [k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_CLIMATE],
    CATEGORY_DOOR: [k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_DOOR],
    CATEGORY_LOCATION: [k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_LOCATION],
    CATEGORY_MOTOR: [k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_MOTOR],
    CATEGORY_TRIP: [k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_TRIP],
    CATEGORY_DEVICE: [k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_DEVICE],
    CATEGORY_DIAGNOSTIC: [k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_DIAGNOSTIC],
    CATEGORY_POWER: [k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_POWER],
    CATEGORY_NETWORK: [k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_NETWORK],
    CATEGORY_SYSTEM: [k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_SYSTEM],
    CATEGORY_TIRE: [k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_TIRE],
}

def get_metric_by_path(metric_path: str) -> Optional[Dict[str, Any]]:
    """Get metric definition by exact path match.
    
    Args:
        metric_path: The metric path to look up
        
    Returns:
        The metric definition or None if not found
    """
    return METRIC_DEFINITIONS.get(metric_path)

def get_metric_by_pattern(topic_parts: List[str]) -> Optional[Dict[str, Any]]:
    """Try to match a metric by pattern in topic parts.
    
    Args:
        topic_parts: List of topic parts to search for patterns
        
    Returns:
        The metric info matching the pattern or None if not found
    """
    # First, try to find an exact match of the last path component
    if topic_parts:
        last_part = topic_parts[-1].lower()
        for pattern, info in TOPIC_PATTERNS.items():
            if pattern == last_part:
                return info
    
    # Then try partial matches in topic parts
    for pattern, info in TOPIC_PATTERNS.items():
        if any(pattern in part.lower() for part in topic_parts):
            return info
    
    return None

def determine_category_from_topic(topic_parts: List[str]) -> str:
    """Determine the most likely category from topic parts.
    
    Args:
        topic_parts: List of topic parts to analyze
        
    Returns:
        The most likely category for this topic
    """
    # Check for known categories in topic
    for part in topic_parts:
        part_lower = part.lower()
        if part_lower in [CATEGORY_BATTERY, CATEGORY_CHARGING, CATEGORY_CLIMATE, 
                          CATEGORY_DOOR, CATEGORY_LOCATION, CATEGORY_MOTOR, 
                          CATEGORY_TRIP, CATEGORY_DIAGNOSTIC, CATEGORY_POWER,
                          CATEGORY_NETWORK, CATEGORY_SYSTEM, CATEGORY_TIRE]:
            return part_lower
    
    # Try matching by prefix
    full_path = ".".join(topic_parts)
    for prefix, category in PREFIX_CATEGORIES.items():
        if full_path.startswith(prefix):
            return category
    
    # Default category
    return CATEGORY_SYSTEM

def create_friendly_name(topic_parts: List[str], metric_info: Optional[Dict[str, Any]] = None) -> str:
    """Create a friendly name from topic parts using metric definitions when available.
    
    Args:
        topic_parts: List of topic parts to use for name creation
        metric_info: Metric info if available
        
    Returns:
        A user-friendly name for the entity
    """
    if not topic_parts:
        return "Unknown"
    
    # If we have metric info, use its name
    if metric_info and "name" in metric_info:
        return metric_info["name"]
    
    # Otherwise, build a name from the last part of the topic
    last_part = topic_parts[-1].replace("_", " ").title()
    
    # If the topic has hierarchical information, include it
    if len(topic_parts) > 1:
        category = determine_category_from_topic(topic_parts)
        return f"{last_part} ({category.title()})"
    
    return last_part
