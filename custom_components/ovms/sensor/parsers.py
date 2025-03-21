"""OVMS sensor state parsers."""
import json
import logging
from typing import Any, Dict, List, Optional

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.util import dt as dt_util

from ..const import LOGGER_NAME

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

def parse_comma_separated_values(value: str) -> Optional[Dict[str, Any]]:
    """Parse comma-separated values into a dictionary with statistics."""
    result = {}
    try:
        # Try to parse all parts as floats
        parts = [float(part.strip()) for part in value.split(",") if part.strip()]
        if parts:
            # Store the array in attributes
            result["cell_values"] = parts
            result["cell_count"] = len(parts)

            # Calculate and store statistics
            result["median"] = calculate_median(parts)
            result["mean"] = sum(parts) / len(parts)
            result["min"] = min(parts)
            result["max"] = max(parts)

            # Store individual cell values with descriptive names
            for i, val in enumerate(parts):
                result[f"cell_{i+1}"] = val

            # Return average as the main value, rounded to 4 decimal places
            result["value"] = round(sum(parts) / len(parts), 4)
            return result
    except (ValueError, TypeError):
        pass
    return None

def parse_value(value: Any, device_class: Optional[Any] = None, state_class: Optional[Any] = None) -> Any:
    """Parse the value from the payload."""
    # Handle special state values for numeric sensors
    if requires_numeric_value(device_class, state_class) and is_special_state_value(value):
        return None

    # Special handling for yes/no values in numeric sensors
    if requires_numeric_value(device_class, state_class) and isinstance(value, str):
        # Convert common boolean strings to numeric values
        if value.lower() in ["no", "off", "false", "disabled"]:
            return 0
        if value.lower() in ["yes", "on", "true", "enabled"]:
            return 1

    # Check if this is a comma-separated list of numbers
    if isinstance(value, str) and "," in value:
        parsed = parse_comma_separated_values(value)
        if parsed:
            return parsed["value"]

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
                return result

            # If we need a numeric value but couldn't extract one, return None
            if requires_numeric_value(device_class, state_class):
                return None
            return str(json_val)

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
            return json_val

        if isinstance(json_val, bool):
            # If we need a numeric value, convert bool to int
            if requires_numeric_value(device_class, state_class):
                return 1 if json_val else 0
            return json_val

        # For arrays or other types, convert to string if not numeric
        if requires_numeric_value(device_class, state_class):
            return None
        return str(json_val)

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
            # Otherwise return as string
            return value

def process_json_payload(payload: str, attributes: Dict[str, Any]) -> Dict[str, Any]:
    """Process JSON payload to extract additional attributes."""
    updated_attributes = attributes.copy()

    try:
        # Check if payload is a comma-separated list of values (cell data)
        if isinstance(payload, str) and "," in payload:
            result = parse_comma_separated_values(payload)
            if result:
                # Add statistical attributes from the result
                for key, value in result.items():
                    if key != "value":  # Skip the main value as we just need attributes
                        updated_attributes[key] = value

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
                    updated_attributes["min_value"] = min(numeric_values)
                    updated_attributes["max_value"] = max(numeric_values)
                    updated_attributes["mean_value"] = sum(numeric_values) / len(numeric_values)
                    updated_attributes["median_value"] = calculate_median(numeric_values)
                except (ValueError, TypeError):
                    # Not all elements are numeric
                    pass

        except (ValueError, json.JSONDecodeError):
            # Not JSON, that's fine
            pass

        # Update timestamp
        updated_attributes["last_updated"] = dt_util.utcnow().isoformat()

    except Exception as ex:
        _LOGGER.exception("Error processing attributes: %s", ex)

    return updated_attributes
