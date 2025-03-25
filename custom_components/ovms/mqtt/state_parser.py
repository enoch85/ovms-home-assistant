"""State parser for OVMS integration."""
import json
import logging
import re
from typing import Any, Dict, List, Optional

from homeassistant.components.sensor import SensorDeviceClass

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

class StateParser:
    """Parser for OVMS state values."""

    @staticmethod
    def parse_value(value: Any, device_class: Optional[Any] = None, state_class: Optional[Any] = None) -> Any:
        """Parse the value from the payload."""
        # Handle special state values for numeric sensors
        if StateParser.requires_numeric_value(device_class, state_class) and StateParser.is_special_state_value(value):
            return None

        # Special handling for yes/no values in numeric sensors
        if StateParser.requires_numeric_value(device_class, state_class) and isinstance(value, str):
            # Convert common boolean strings to numeric values
            if value.lower() in ["no", "off", "false", "disabled"]:
                return 0
            if value.lower() in ["yes", "on", "true", "enabled"]:
                return 1

        # Check if this is a comma-separated list of numbers (including negative numbers)
        if isinstance(value, str) and "," in value:
            try:
                # Try to parse all parts as floats
                parts = [float(part.strip()) for part in value.split(",") if part.strip()]
                if parts:
                    # Calculate and return statistics
                    avg_value = sum(parts) / len(parts)
                    # Return the average as the main value, rounded to 4 decimal places
                    return round(avg_value, 4)
            except (ValueError, TypeError):
                # If any part can't be converted to float, fall through to other methods
                pass

        # Try parsing as JSON first
        try:
            json_val = json.loads(value)

            # Handle special JSON values
            if StateParser.is_special_state_value(json_val):
                return None

        # Check if the value has units embedded in the string (like -101dBm)
        if isinstance(value, str) and any(u in value for u in ["dBm", "V", "A", "W", "°C", "km", "Sec"]):
            numeric_value = StateParser.extract_numeric_from_string(value)
            if numeric_value is not None:
                return numeric_value

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
                if StateParser.is_special_state_value(result):
                    return None

                # If we have a result, return it; otherwise fall back to string representation
                if result is not None:
                    return result

                # If we need a numeric value but couldn't extract one, return None
                if StateParser.requires_numeric_value(device_class, state_class):
                    return None
                return str(json_val)

            # If JSON is a scalar, use it directly
            if isinstance(json_val, (int, float)):
                return json_val

            if isinstance(json_val, str):
                # Handle special string values
                if StateParser.is_special_state_value(json_val):
                    return None

                # If we need a numeric value but got a string, try to convert it
                if StateParser.requires_numeric_value(device_class, state_class):
                    try:
                        return float(json_val)
                    except (ValueError, TypeError):
                        return None
                return json_val

            if isinstance(json_val, bool):
                # If we need a numeric value, convert bool to int
                if StateParser.requires_numeric_value(device_class, state_class):
                    return 1 if json_val else 0
                return json_val

            # For arrays or other types, convert to string if not numeric
            if StateParser.requires_numeric_value(device_class, state_class):
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
                if StateParser.requires_numeric_value(device_class, state_class):
                    return None
                # Otherwise return as string
                return value

    @staticmethod
    def parse_binary_state(value: Any) -> bool:
        """Parse the state string to a boolean."""
        try:
            if isinstance(value, str):
                if value.lower() in ("true", "on", "yes", "1", "open", "locked"):
                    return True
                if value.lower() in ("false", "off", "no", "0", "closed", "unlocked"):
                    return False

    @staticmethod
    def extract_numeric_from_string(value: str) -> Optional[float]:
        """Extract a numeric value from a string with units."""
        if not isinstance(value, str):
            return None

        # Common patterns for values with units
        patterns = [
            r'(-?\d+\.?\d*)dBm',  # Signal strength
            r'(-?\d+\.?\d*)V',    # Voltage
            r'(-?\d+\.?\d*)A',    # Current
            r'(-?\d+\.?\d*)W',    # Power
            r'(-?\d+\.?\d*)°C',   # Temperature
            r'(-?\d+\.?\d*)km',   # Distance
            r'(-?\d+\.?\d*)Sec',  # Time
        ]

        for pattern in patterns:
            match = re.search(pattern, value)
            if match:
                try:
                    return float(match.group(1))
                except (ValueError, IndexError):
                    continue

        return None

            # Try numeric comparison
            try:
                return float(value) > 0
            except (ValueError, TypeError):
                return False
        except Exception as ex:
            _LOGGER.exception("Error parsing binary state '%s': %s", value, ex)
            return False

    @staticmethod
    def extract_attributes_from_json(value: Any) -> Dict[str, Any]:
        """Extract attributes from a JSON payload."""
        attributes = {}
        try:
            json_data = json.loads(value) if isinstance(value, str) else value
            if isinstance(json_data, dict):
                # Add useful attributes from the data
                for key, val in json_data.items():
                    if key not in ["value", "state", "data"]:
                        attributes[key] = val

                # If there's a timestamp in the JSON, use it
                if "timestamp" in json_data:
                    attributes["device_timestamp"] = json_data["timestamp"]
        except (ValueError, json.JSONDecodeError):
            # Not JSON, that's fine
            pass
        return attributes

    @staticmethod
    def requires_numeric_value(device_class: Any, state_class: Any) -> bool:
        """Check if this sensor requires a numeric value based on its device class."""
        return (
            device_class in NUMERIC_DEVICE_CLASSES or
            state_class in [
                "measurement",
                "total",
                "total_increasing"
            ]
        )

    @staticmethod
    def is_special_state_value(value: Any) -> bool:
        """Check if a value is a special state value that should be converted to None."""
        if value is None:
            return True
        if isinstance(value, str) and value.lower() in SPECIAL_STATE_VALUES:
            return True
        return False

    @staticmethod
    def calculate_statistics(values: List[float]) -> Dict[str, float]:
        """Calculate statistics for a list of values."""
        if not values:
            return {}

        try:
            # Calculate basic statistics
            stats = {
                "average": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
                "count": len(values),
            }

            # Calculate median
            sorted_values = sorted(values)
            n = len(sorted_values)
            if n % 2 == 0:
                stats["median"] = (sorted_values[n//2 - 1] + sorted_values[n//2]) / 2
            else:
                stats["median"] = sorted_values[n//2]

            return stats

        except Exception as ex:
            _LOGGER.exception("Error calculating statistics: %s", ex)
            return {}

    @staticmethod
    def parse_gps_coordinates(payload: Any) -> Dict[str, Any]:
        """Parse GPS coordinates from payload."""
        try:
            # Check for direct float values
            if isinstance(payload, (int, float)):
                return {"value": float(payload)}

            # Try JSON parsing
            try:
                data = json.loads(payload) if isinstance(payload, str) else payload
                if isinstance(data, dict):
                    if "latitude" in data and "longitude" in data:
                        return {
                            "latitude": float(data["latitude"]),
                            "longitude": float(data["longitude"]),
                            "gps_accuracy": data.get("gps_accuracy", 0),
                        }
                    else:
                        # Extract any single value
                        for key, value in data.items():
                            if isinstance(value, (int, float)):
                                return {"value": float(value)}
            except (ValueError, json.JSONDecodeError):
                pass

            # Try direct string conversion
            if isinstance(payload, str):
                try:
                    return {"value": float(payload.strip())}
                except (ValueError, TypeError):
                    pass

            return {}

        except Exception as ex:
            _LOGGER.exception("Error parsing GPS coordinates: %s", ex)
            return {}
