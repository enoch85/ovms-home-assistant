"""Dynamic entity handling for OVMS MQTT integration."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple, Union

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfPower,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfVolume,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import slugify

from .const import DOMAIN, DEFAULT_MANUFACTURER

_LOGGER = logging.getLogger(__name__)

# Device class hints based on keywords in topic or value
DEVICE_CLASS_HINTS = {
    # Topic or value contains -> device class
    "soc": SensorDeviceClass.BATTERY,
    "battery": SensorDeviceClass.BATTERY,
    "range": SensorDeviceClass.DISTANCE,
    "distance": SensorDeviceClass.DISTANCE,
    "power": SensorDeviceClass.POWER,
    "current": SensorDeviceClass.CURRENT,
    "voltage": SensorDeviceClass.VOLTAGE,
    "temp": SensorDeviceClass.TEMPERATURE,
    "temperature": SensorDeviceClass.TEMPERATURE,
    "energy": SensorDeviceClass.ENERGY,
    "latitude": SensorDeviceClass.LATITUDE,
    "longitude": SensorDeviceClass.LONGITUDE,
    "altitude": SensorDeviceClass.DISTANCE,
    "speed": SensorDeviceClass.SPEED,
    "odometer": SensorDeviceClass.DISTANCE,
    "trip": SensorDeviceClass.DISTANCE,
    "efficiency": SensorDeviceClass.POWER_FACTOR,
    "duration": SensorDeviceClass.DURATION,
    "consumption": SensorDeviceClass.ENERGY,
}

# Unit hints based on keywords in topic
UNIT_HINTS = {
    "soc": PERCENTAGE,
    "range": UnitOfLength.KILOMETERS,
    "distance": UnitOfLength.KILOMETERS,
    "voltage": UnitOfElectricPotential.VOLT,
    "current": UnitOfElectricCurrent.AMPERE,
    "power": UnitOfPower.KILO_WATT,
    "energy": UnitOfEnergy.KILO_WATT_HOUR,
    "temp": UnitOfTemperature.CELSIUS,
    "temperature": UnitOfTemperature.CELSIUS,
    "speed": UnitOfSpeed.KILOMETERS_PER_HOUR,
    "odometer": UnitOfLength.KILOMETERS,
    "trip": UnitOfLength.KILOMETERS,
}

# Common unit strings that might be in the payload
UNIT_MAPPINGS = {
    'km': UnitOfLength.KILOMETERS,
    'mi': UnitOfLength.MILES,
    'kWh': UnitOfEnergy.KILO_WATT_HOUR,
    'Wh': UnitOfEnergy.WATT_HOUR,
    'V': UnitOfElectricPotential.VOLT,
    'A': UnitOfElectricCurrent.AMPERE,
    'kW': UnitOfPower.KILO_WATT,
    'W': UnitOfPower.WATT,
    'C': UnitOfTemperature.CELSIUS,
    'F': UnitOfTemperature.FAHRENHEIT,
    '%': PERCENTAGE,
    'L': UnitOfVolume.LITERS,
    'gal': UnitOfVolume.GALLONS,
    'km/h': UnitOfSpeed.KILOMETERS_PER_HOUR,
    'mph': UnitOfSpeed.MILES_PER_HOUR,
}

# State class hints based on keywords in topic
STATE_CLASS_HINTS = {
    "soc": SensorStateClass.MEASUREMENT,
    "range": SensorStateClass.MEASUREMENT,
    "power": SensorStateClass.MEASUREMENT,
    "current": SensorStateClass.MEASUREMENT,
    "voltage": SensorStateClass.MEASUREMENT,
    "temp": SensorStateClass.MEASUREMENT,
    "temperature": SensorStateClass.MEASUREMENT,
    "odometer": SensorStateClass.TOTAL_INCREASING,
    "consumption": SensorStateClass.TOTAL_INCREASING,
    "trip": SensorStateClass.TOTAL_INCREASING,
    "energy/used": SensorStateClass.TOTAL_INCREASING,
    "energy/recovered": SensorStateClass.TOTAL_INCREASING,
    "charge": SensorStateClass.TOTAL_INCREASING,
}

# State class pattern matching for more complex cases
STATE_CLASS_PATTERNS = [
    # Format: (keyword, suffixes/context, state_class)
    ("energy", ["used", "consumed", "total"], SensorStateClass.TOTAL_INCREASING),
    ("energy", ["rate", "current"], SensorStateClass.MEASUREMENT),
    ("power", [], SensorStateClass.MEASUREMENT),
    ("soc", [], SensorStateClass.MEASUREMENT),
    ("temperature", [], SensorStateClass.MEASUREMENT),
]

# Icon hints based on keywords in topic
ICON_HINTS = {
    "soc": "mdi:battery",
    "battery": "mdi:battery",
    "range": "mdi:map-marker-distance",
    "distance": "mdi:map-marker-distance",
    "power": "mdi:flash",
    "current": "mdi:current-ac",
    "voltage": "mdi:flash",
    "temp": "mdi:thermometer",
    "temperature": "mdi:thermometer",
    "energy": "mdi:battery-charging",
    "charging": "mdi:battery-charging",
    "location": "mdi:map-marker",
    "latitude": "mdi:latitude",
    "longitude": "mdi:longitude",
    "altitude": "mdi:altitude",
    "speed": "mdi:speedometer",
    "direction": "mdi:compass",
    "odometer": "mdi:counter",
    "trip": "mdi:map-marker-distance",
    "consumption": "mdi:chart-line",
    "efficiency": "mdi:chart-line",
    "duration": "mdi:timer",
    "limit": "mdi:speedometer",
    "door": "mdi:car-door",
    "lock": "mdi:lock",
}

# Device category hints based on topic path segments
DEVICE_CATEGORY_HINTS = {
    "b": "Battery",
    "c": "Charging",
    "d": "Drive",
    "e": "Energy & Environment",
    "p": "Position & Motion",
    "t": "Tire Pressure",
    "i": "Identification",
    "s": "Status",
    "v": "Vehicle",
}


def get_device_info(vehicle_id: str, category: str) -> DeviceInfo:
    """Get device info for specified vehicle and category."""
    # Get friendly category name
    if category in DEVICE_CATEGORY_HINTS:
        category_name = DEVICE_CATEGORY_HINTS[category]
    else:
        category_name = category.replace("_", " ").title()
    
    # Create category-specific identifier
    identifier = f"{slugify(vehicle_id)}_{slugify(category_name)}"
    
    return DeviceInfo(
        identifiers={(DOMAIN, identifier)},
        name=f"{vehicle_id} - {category_name}",
        manufacturer=DEFAULT_MANUFACTURER,
        model="OVMS Vehicle",
        via_device=(DOMAIN, slugify(vehicle_id)),
    )


def get_vehicle_device_info(vehicle_id: str) -> DeviceInfo:
    """Get the main vehicle device info."""
    return DeviceInfo(
        identifiers={(DOMAIN, slugify(vehicle_id))},
        name=f"{vehicle_id}",
        manufacturer=DEFAULT_MANUFACTURER,
        model="OVMS Vehicle",
    )


def get_battery_icon(level: Union[int, float]) -> str:
    """Get the appropriate battery icon for the given level."""
    try:
        level_int = int(float(level))
        if level_int <= 10:
            return "mdi:battery-10"
        elif level_int <= 20:
            return "mdi:battery-20"
        elif level_int <= 30:
            return "mdi:battery-30"
        elif level_int <= 40:
            return "mdi:battery-40"
        elif level_int <= 50:
            return "mdi:battery-50"
        elif level_int <= 60:
            return "mdi:battery-60"
        elif level_int <= 70:
            return "mdi:battery-70"
        elif level_int <= 80:
            return "mdi:battery-80"
        elif level_int <= 90:
            return "mdi:battery-90"
        else:
            return "mdi:battery"
    except (ValueError, TypeError):
        # Default to regular battery icon if conversion fails
        return "mdi:battery"


def parse_topic(topic: str) -> Tuple[Optional[str], Optional[str], list, Optional[str]]:
    """Parse an OVMS topic into components.
    
    Returns:
        Tuple with (vehicle_id, topic_type, path_segments, metric_name)
    """
    if not topic:
        return None, None, [], None
    
    try:
        parts = topic.split('/')
        
        # Need at least: prefix/vehicleid/vin/...
        if len(parts) < 4:
            return None, None, [], None
        
        # Assume parts[0] is the configured topic prefix (e.g., "ovms")
        vehicle_id = parts[2]  # The VIN
        
        # Check if this is a metric topic
        if len(parts) >= 5 and parts[3] == "metric":
            topic_type = "metric"
            path_segments = parts[4:-1] if len(parts) > 5 else []
            metric_name = parts[-1]
        else:
            topic_type = parts[3] if len(parts) > 3 else None
            path_segments = parts[4:-1] if len(parts) > 4 else []
            metric_name = parts[-1] if len(parts) > 4 else None
        
        return vehicle_id, topic_type, path_segments, metric_name
    except Exception as e:
        _LOGGER.error("Error parsing topic %s: %s", topic, e)
        return None, None, [], None


def determine_entity_metadata(
    topic: str, path_segments: list, metric_name: str, payload_data: Any
) -> dict:
    """Determine entity metadata from topic and payload."""
    result = {
        "name": metric_name.replace('_', ' ').title() if metric_name else "Unknown",
        "value": None,
        "unit": None,
        "device_class": None,
        "state_class": None,
        "icon": None,
        "category": path_segments[0] if path_segments else None,
    }
    
    # Extract value from payload
    if isinstance(payload_data, dict):
        # If it's a dictionary, look for value and unit
        if "value" in payload_data:
            result["value"] = payload_data["value"]
        elif "state" in payload_data:
            result["value"] = payload_data["state"]
        else:
            # Use the first value that's not a unit or timestamp
            for key, value in payload_data.items():
                if key != "unit" and key != "timestamp" and key != "t":
                    result["value"] = value
                    break
        
        # Extract unit if present
        if "unit" in payload_data:
            unit = payload_data["unit"]
            # Map to HA units if possible
            result["unit"] = UNIT_MAPPINGS.get(unit, unit)
    else:
        # If it's a simple value
        result["value"] = payload_data
    
    # If there's no value, we can't create a sensor
    if result["value"] is None:
        return result
    
    # Combine topic parts for keyword matching
    full_topic_lower = topic.lower()
    
    # Try to determine device class from topic keywords
    for keyword, device_class in DEVICE_CLASS_HINTS.items():
        if keyword in full_topic_lower:
            result["device_class"] = device_class
            break
    
    # Try to determine state class from topic keywords
    for keyword, state_class in STATE_CLASS_HINTS.items():
        if keyword in full_topic_lower:
            result["state_class"] = state_class
            break
            
    # If no state class found, try more complex pattern matching
    if not result["state_class"]:
        for base_keyword, contexts, state_class in STATE_CLASS_PATTERNS:
            if base_keyword in full_topic_lower:
                # If no specific contexts to check, or if any context matches
                if not contexts or any(ctx in full_topic_lower for ctx in contexts):
                    result["state_class"] = state_class
                    break
    
    # Try to determine icon from topic keywords
    for keyword, icon in ICON_HINTS.items():
        if keyword in full_topic_lower:
            result["icon"] = icon
            break
    
    # If unit not in payload, try to determine from topic
    if not result["unit"]:
        # Try to find unit from topic hints
        for keyword, unit in UNIT_HINTS.items():
            if keyword in full_topic_lower:
                result["unit"] = unit
                break
    
    # For battery SOC, adjust icon based on level
    if "soc" in full_topic_lower and isinstance(result["value"], (int, float)):
        result["icon"] = get_battery_icon(result["value"])
    
    return result


def process_ovms_message(topic: str, payload: bytes) -> Optional[Dict[str, Any]]:
    """Process an OVMS MQTT message and extract entity data."""
    try:
        # Parse topic
        vehicle_id, topic_type, path_segments, metric_name = parse_topic(topic)
        if not vehicle_id:
            return None
        
        # Parse payload
        try:
            payload_data = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            # If not JSON, use raw payload as string
            try:
                payload_data = payload.decode("utf-8").strip()
            except UnicodeDecodeError:
                _LOGGER.warning("Could not decode payload for topic %s", topic)
                return None
        
        # Process the metric value and metadata
        metadata = determine_entity_metadata(
            topic, path_segments, metric_name, payload_data
        )
        if metadata["value"] is None:
            return None
        
        # Create unique ID - use the full topic path to ensure uniqueness
        unique_id = f"{slugify(vehicle_id)}_{slugify(topic.replace('/', '_'))}"
        
        # Create entity data
        entity_data = {
            "unique_id": unique_id,
            "name": metadata["name"],
            "state": metadata["value"],
            "unit": metadata["unit"],
            "device_class": metadata["device_class"],
            "state_class": metadata["state_class"],
            "icon": metadata["icon"],
            "vehicle_id": vehicle_id,
            "topic": topic,
            "category": metadata["category"],
            "last_updated": datetime.now().isoformat(),
        }
        
        return entity_data
    
    except Exception as e:
        _LOGGER.exception("Error processing OVMS message: %s", e)
        return None
