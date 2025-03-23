"""OVMS sensor state parsers."""
import json
import logging
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
from homeassistant.util import dt as dt_util

from ..const import LOGGER_NAME, MAX_STATE_LENGTH, truncate_state_value

_LOGGER = logging.getLogger(LOGGER_NAME)

# List of device classes that should have numeric values
NUMERIC_DEVICE_CLASSES = [
    SensorDeviceClass.BATTERY,
    SensorDeviceClass.CURRENT,
    SensorDeviceClass.ENERGY,
    SensorDeviceClass.HUMIDITY,
    SensorDeviceClass.POWER,
    SensorDeviceClass.TEMPERATURE,
    SensorDeviceClass.VOLTAGE,
    SensorDeviceClass.DISTANCE,
    SensorDeviceClass.SPEED,
    SensorDeviceClass.DURATION,  # Added duration to numeric device classes
]

# Special string values that should be converted to None for numeric sensors
SPECIAL_STATE_VALUES = ["unavailable", "unknown", "none", "", "null", "nan"]


def requires_numeric_value(device_class: Any, state_class: Any) -> bool:
    """Check if this sensor requires a numeric value based on its device class."""
    return (
        device_class in NUMERIC_DEVICE_CLASSES or
        state_class in [
            SensorStateClass.MEASUREMENT,
            SensorStateClass.TOTAL,
            SensorStateClass.TOTAL_INCREASING
        ]
    )

def is_special_state_value(value) -> bool:
    """Check if a value is a special state value that should be converted to None."""
    if value is None:
        return True
    if isinstance(value, str) and value.lower() in SPECIAL_STATE_VALUES:
        return True
    return False

def calculate_median(values: List[float]) -> Optional[float]:
    """Calculate the median of a list of values."""
    if not values:
        return None
    sorted_values = sorted(values)
    n = len(sorted_values)
    if n % 2 == 0:
        return (sorted_values[n//2 - 1] + sorted_values[n//2]) / 2
    return sorted_values[n//2]

def parse_comma_separated_values(value: str, entity_name: str = "", is_cell_sensor: bool = False, stat_type: str = "cell") -> Optional[Dict[str, Any]]:
    """Parse comma-separated values into a dictionary with statistics.
    
    Args:
        value: The comma-separated string of values
        entity_name: The name of the entity for determining attribute type
        is_cell_sensor: Whether this is a cell-type sensor (battery cells, etc)
        stat_type: The specific attribute type to use (voltage, temp, etc)
    """
    if not is_cell_sensor:
        return None  # Skip processing if not a cell sensor
        
    result = {}
    try:
        # Try to parse all parts as floats
        parts = [float(part.strip()) for part in value.split(",") if part.strip()]
        if parts:
            # Store the array in attributes - use only one consistent naming
            result[f"{stat_type}_values"] = parts
            result["count"] = len(parts)

            # Calculate and store statistics
            result["median"] = calculate_median(parts)
            result["mean"] = sum(parts) / len(parts)
            result["min"] = min(parts)
            result["max"] = max(parts)

            # Store individual values with descriptive names
            for i, val in enumerate(parts):
                result[f"{stat_type}_{i+1}"] = val

            # Return average as the main value, rounded to 4 decimal places
            result["value"] = round(sum(parts) / len(parts), 4)
            return result
    except (ValueError, TypeError):
        pass
    return None

def parse_value(value: Any, device_class: Optional[Any] = None, state_class: Optional[Any] = None, 
                is_cell_sensor: bool = False) -> Any:
    """Parse the value from the payload."""
    # Handle special state values for numeric sensors
    if requires_numeric_value(device_class, state_class) and is_special_state_value(value):
        return None

    # Special handling for duration values - convert to seconds for HA
    if device_class == SensorDeviceClass.DURATION:
        # Extract numeric value - could be direct or in JSON
        numeric_value = _extract_numeric_value(value)
        if numeric_value is not None:
            # Look for unit hints in the payload
            unit_hint = _get_unit_hint(value)
            
            # Convert to seconds based on unit hint
            if unit_hint == UnitOfTime.MINUTES:
                return numeric_value * 60
            elif unit_hint == UnitOfTime.HOURS:
                return numeric_value * 3600
            elif unit_hint == UnitOfTime.DAYS:
                return numeric_value * 86400
            # Default to seconds if no unit hint or already in seconds
            return numeric_value

    # Special handling for yes/no values in numeric sensors
    if requires_numeric_value(device_class, state_class) and isinstance(value, str):
        # Convert common boolean strings to numeric values
        if value.lower() in ["no", "off", "false", "disabled"]:
            return 0
        if value.lower() in ["yes", "on", "true", "enabled"]:
            return 1

    # Check if this is a comma-separated list of numbers for a cell sensor
    if is_cell_sensor and isinstance(value, str) and "," in value:
        # For cell sensors with comma separated values, we'll extract the average
        # as the state but this will be handled by _handle_cell_values 
        # for attribute processing
        try:
            values = [float(part.strip()) for part in value.split(",") if part.strip()]
            if values:
                return round(sum(values) / len(values), 4)
        except (ValueError, TypeError):
            pass

    # Try parsing as JSON first
    try:
        json_val = json.loads(value)

        # Handle special JSON values
        if is_special_state_value(json_val):
            return None

        # If JSON is a dict, extract likely value
        if isinstance(json_val, dict):
            result = None
            if "value" in json_val:
                result = json_val["value"]
            elif "state" in json_val:
                result = json_val["state"]
            else:
                # Return first numeric value found
                for key, val in json_val.items():
                    if isinstance(val, (int, float)):
                        result = val
                        break

            # Handle special values in result
            if is_special_state_value(result):
                return None

            # If we have a result, return it; otherwise fall back to string representation
            if result is not None:
                return truncate_state_value(result)

            # If we need a numeric value but couldn't extract one, return None
            if requires_numeric_value(device_class, state_class):
                return None
            return truncate_state_value(str(json_val))

        # If JSON is a scalar, use it directly
        if isinstance(json_val, (int, float)):
            return json_val

        if isinstance(json_val, str):
            # Handle special string values
            if is_special_state_value(json_val):
                return None

            # If we need a numeric value but got a string, try to convert it
            if requires_numeric_value(device_class, state_class):
                try:
                    return float(json_val)
                except (ValueError, TypeError):
                    return None
            return truncate_state_value(json_val)

        if isinstance(json_val, bool):
            # If we need a numeric value, convert bool to int
            if requires_numeric_value(device_class, state_class):
                return 1 if json_val else 0
            return json_val

        # For arrays or other types, convert to string if not numeric
        if requires_numeric_value(device_class, state_class):
            return None
        return truncate_state_value(str(json_val))

    except (ValueError, json.JSONDecodeError):
        # Not JSON, try numeric
        try:
            # Check if it's a float
            if isinstance(value, str) and "." in value:
                return float(value)
            # Check if it's an int
            return int(value)
        except (ValueError, TypeError):
            # If we need a numeric value but couldn't convert, return None
            if requires_numeric_value(device_class, state_class):
                return None
            # Otherwise return as string with truncation if needed
            return truncate_state_value(value)

def _extract_numeric_value(value: Any) -> Optional[float]:
    """Extract a numeric value from various input formats."""
    # Direct numeric value
    if isinstance(value, (int, float)):
        return float(value)
    
    # String value that can be converted directly
    if isinstance(value, str):
        try:
            return float(value.strip())
        except (ValueError, TypeError):
            pass
            
    # JSON encoded value
    try:
        if isinstance(value, str):
            json_val = json.loads(value)
            if isinstance(json_val, (int, float)):
                return float(json_val)
            elif isinstance(json_val, dict):
                for key in ['value', 'state', 'duration']:
                    if key in json_val and isinstance(json_val[key], (int, float)):
                        return float(json_val[key])
    except (ValueError, json.JSONDecodeError):
        pass
        
    return None

def _get_unit_hint(value: Any) -> Optional[str]:
    """Try to determine the time unit from the payload."""
    # Check for unit in JSON
    try:
        if isinstance(value, str):
            json_val = json.loads(value)
            if isinstance(json_val, dict):
                # Look for unit field
                if 'unit' in json_val:
                    unit = str(json_val['unit']).lower()
                    if 'min' in unit:
                        return UnitOfTime.MINUTES
                    elif 'hour' in unit or 'hr' in unit:
                        return UnitOfTime.HOURS
                    elif 'day' in unit:
                        return UnitOfTime.DAYS
                    elif 'sec' in unit:
                        return UnitOfTime.SECONDS
                        
                # Check field names for hints
                for key in json_val.keys():
                    key_lower = key.lower()
                    if 'minute' in key_lower or 'min' in key_lower:
                        return UnitOfTime.MINUTES
                    elif 'hour' in key_lower or 'hr' in key_lower:
                        return UnitOfTime.HOURS
                    elif 'day' in key_lower:
                        return UnitOfTime.DAYS
                    elif 'second' in key_lower or 'sec' in key_lower:
                        return UnitOfTime.SECONDS
    except (ValueError, json.JSONDecodeError):
        pass
    
    # Check for unit hints in string form
    if isinstance(value, str):
        if 'min' in value.lower():
            return UnitOfTime.MINUTES
        elif 'hour' in value.lower() or 'hr' in value.lower():
            return UnitOfTime.HOURS
        elif 'day' in value.lower():
            return UnitOfTime.DAYS
        elif 'sec' in value.lower():
            return UnitOfTime.SECONDS
            
    # Default to seconds as most metrics use this
    return UnitOfTime.SECONDS

def process_json_payload(payload: str, attributes: Dict[str, Any], entity_name: str = "", 
                        is_cell_sensor: bool = False, stat_type: str = "cell") -> Dict[str, Any]:
    """Process JSON payload to extract additional attributes.
    
    Args:
        payload: The payload to process
        attributes: Existing attributes to update
        entity_name: The name of the entity for determining attribute type
        is_cell_sensor: Whether this is a cell-type sensor (battery cells, etc)
        stat_type: The specific attribute type to use (voltage, temp, etc)
    """
    updated_attributes = attributes.copy()

    try:
        # Skip cell value processing here - handled by _handle_cell_values instead
        # to avoid duplication of processing
        if not (is_cell_sensor and isinstance(payload, str) and "," in payload):
            # Try to parse as JSON
            try:
                json_data = json.loads(payload) if isinstance(payload, str) else payload
                if isinstance(json_data, dict):
                    # Add all fields as attributes
                    for key, value in json_data.items():
                        if key not in ["value", "state", "data"] and key not in updated_attributes:
                            updated_attributes[key] = value

                    # If there's a timestamp in the JSON, use it
                    if "timestamp" in json_data:
                        updated_attributes["device_timestamp"] = json_data["timestamp"]

                    # If there's a unit in the JSON, use it for native unit
                    if "unit" in json_data and "unit_of_measurement" not in updated_attributes:
                        updated_attributes["unit"] = json_data["unit"]

                    # Extract and add any nested attributes
                    for key, value in json_data.items():
                        if isinstance(value, dict):
                            for subkey, subvalue in value.items():
                                attr_key = f"{key}_{subkey}"
                                if attr_key not in updated_attributes:
                                    updated_attributes[attr_key] = subvalue

                # If JSON is an array, add array attributes
                elif isinstance(json_data, list):
                    updated_attributes["list_values"] = json_data
                    updated_attributes["list_length"] = len(json_data)

                    # Try to convert to numbers and add statistics
                    try:
                        numeric_values = [float(val) for val in json_data]
                        updated_attributes["min"] = min(numeric_values)
                        updated_attributes["max"] = max(numeric_values)
                        updated_attributes["mean"] = sum(numeric_values) / len(numeric_values)
                        updated_attributes["median"] = calculate_median(numeric_values)
                    except (ValueError, TypeError):
                        # Not all elements are numeric
                        pass

            except (ValueError, json.JSONDecodeError):
                # Not JSON, that's fine
                pass

        # Update timestamp
        updated_attributes["last_updated"] = dt_util.utcnow().isoformat()
        
        # Add full topic path for debugging
        if "topic" in attributes:
            updated_attributes["full_topic"] = attributes["topic"]

    except Exception as ex:
        _LOGGER.exception("Error processing attributes: %s", ex)

    return updated_attributes
