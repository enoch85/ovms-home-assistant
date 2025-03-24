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
    UnitOfTime,
)
from homeassistant.helpers.entity import EntityCategory

from ..const import LOGGER_NAME
from ..metrics import get_metric_by_path, get_metric_by_pattern, METRIC_DEFINITIONS

_LOGGER = logging.getLogger(LOGGER_NAME)

# A mapping of sensor name patterns to device classes and units
SENSOR_TYPES = {
    "soc": {
        "device_class": SensorDeviceClass.BATTERY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "icon": "mdi:battery",
    },
    "range": {
        "device_class": SensorDeviceClass.DISTANCE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfLength.KILOMETERS,
        "icon": "mdi:map-marker-distance",
    },
    "temperature": {
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer",
    },
    "power": {
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
        "icon": "mdi:flash",
    },
    "current": {
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricCurrent.AMPERE,
        "icon": "mdi:current-ac",
    },
    "voltage": {
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "icon": "mdi:flash",
    },
    "energy": {
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "icon": "mdi:battery-charging",
    },
    "speed": {
        "device_class": SensorDeviceClass.SPEED,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfSpeed.KILOMETERS_PER_HOUR,
        "icon": "mdi:speedometer",
    },
    "timestamp": {
        "device_class": SensorDeviceClass.TIMESTAMP,
        "icon": "mdi:clock",
    },
    # Additional icons for EV-specific metrics
    "odometer": {
        "icon": "mdi:counter",
        "state_class": SensorStateClass.TOTAL_INCREASING,
    },
    "efficiency": {
        "icon": "mdi:leaf",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "climate": {
        "icon": "mdi:fan",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "hvac": {
        "icon": "mdi:air-conditioner",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "motor": {
        "icon": "mdi:engine",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "trip": {
        "icon": "mdi:map-marker-path",
        "state_class": SensorStateClass.MEASUREMENT,
    },
    # Diagnostic sensors
    "status": {
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:information-outline",
    },
    "signal": {
        "entity_category": EntityCategory.DIAGNOSTIC,
        "device_class": SensorDeviceClass.SIGNAL_STRENGTH,
        "icon": "mdi:signal",
    },
    "firmware": {
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:package-up",
    },
    "version": {
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:tag-text",
    },
    "task": {
        "entity_category": EntityCategory.DIAGNOSTIC,
        "icon": "mdi:list-status",
    }
}

# Set of all known duration metric paths for easier lookup
DURATION_METRIC_PATHS = {
    k for k, v in METRIC_DEFINITIONS.items() 
    if v.get("device_class") == SensorDeviceClass.DURATION
}

def get_duration_metric_unit(metric_path: str) -> Optional[str]:
    """Find the appropriate unit for a duration metric based on its path.
    
    First checks the metric definitions, then applies standard rules for known duration metrics.
    """
    from homeassistant.const import UnitOfTime
    
    # Check if this exact path is in metrics definitions
    if metric_path in METRIC_DEFINITIONS:
        metric = METRIC_DEFINITIONS[metric_path]
        if "unit" in metric:
            return metric["unit"]
    
    # Try partial path matches for metrics with device_class = duration
    for duration_path in DURATION_METRIC_PATHS:
        if duration_path.endswith(metric_path) or metric_path.endswith(duration_path):
            metric = METRIC_DEFINITIONS[duration_path]
            if "unit" in metric:
                return metric["unit"]
    
    # Apply standard rules for different types of duration metrics
    if any(segment in metric_path for segment in ["drivetime", "parktime", "time", "monotonic"]):
        return UnitOfTime.SECONDS
    elif "duration" in metric_path:
        # Special cases for duration metrics
        if any(segment in metric_path for segment in ["full", "range", "soc"]):
            return UnitOfTime.MINUTES
        else:
            return UnitOfTime.SECONDS
    elif "day" in metric_path:
        return UnitOfTime.DAYS
        
    # Default for unknown duration metrics
    return UnitOfTime.SECONDS

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
        # Also apply diagnostic entity category to network and system sensors
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

    # Try to find matching metric by converting topic to dot notation
    topic_suffix = topic
    if topic.count('/') >= 3:  # Skip the prefix part
        parts = topic.split('/')
        # Find where the actual metric path starts
        for i, part in enumerate(parts):
            if part in ["metric", "status", "notify", "command", "m", "v", "s", "t"]:
                topic_suffix = '/'.join(parts[i:])
                break

    metric_path = topic_suffix.replace("/", ".")

    # Try exact match first
    metric_info = get_metric_by_path(metric_path)

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

    # Check if this looks like a duration sensor by topic pattern
    duration_keywords = ["drivetime", "parktime", "charging/time", "time", "duration", "monotonic", "g/time"]
    if result["device_class"] is None and any(keyword in topic for keyword in duration_keywords):
        result["device_class"] = SensorDeviceClass.DURATION
        result["state_class"] = SensorStateClass.MEASUREMENT
        
    # Ensure duration sensors always have a unit 
    if result["device_class"] == SensorDeviceClass.DURATION and not result["native_unit_of_measurement"]:
        # Look up the appropriate unit using our helper function
        result["native_unit_of_measurement"] = get_duration_metric_unit(metric_path)

    # If no metric info was found, use the original pattern matching as fallback
    if result["device_class"] is None:
        for key, sensor_type in SENSOR_TYPES.items():
            if key in internal_name.lower() or key in topic.lower():
                if "device_class" in sensor_type:
                    result["device_class"] = sensor_type["device_class"]
                if "state_class" in sensor_type:
                    result["state_class"] = sensor_type["state_class"]
                if "unit" in sensor_type:
                    result["native_unit_of_measurement"] = sensor_type["unit"]
                if "entity_category" in sensor_type:
                    result["entity_category"] = sensor_type["entity_category"]
                if "icon" in sensor_type:
                    result["icon"] = sensor_type["icon"]
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

        elif device_class == SensorDeviceClass.DURATION:
            # Only add unit if not already defined
            if "unit_of_measurement" not in updated_attrs and "unit" not in updated_attrs:
                # Check topic for the specific metric to determine unit
                topic = str(updated_attrs.get("topic", ""))
                
                # Extract the metric path for lookup
                topic_suffix = topic
                if topic.count('/') >= 3:
                    parts = topic.split('/')
                    for i, part in enumerate(parts):
                        if part in ["metric", "status", "notify", "command", "m", "v", "s", "t"]:
                            topic_suffix = '/'.join(parts[i:])
                            break
                metric_path = topic_suffix.replace("/", ".")
                
                # Get the appropriate unit based on the metric path
                updated_attrs["unit"] = get_duration_metric_unit(metric_path)
                    
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
