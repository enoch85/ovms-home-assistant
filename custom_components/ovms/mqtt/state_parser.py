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
    def parse_value(value: Any, device_class: Optional[Any] = None, state_class: Optional[Any] = None,
                   topic: str = "") -> Any:
        """Parse the value from the payload with enhanced precision and validation."""
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
            # Check if this is cell data that should NOT be averaged
            is_cell_data = StateParser._is_cell_data_topic(topic)
            
            _LOGGER.debug(f"StateParser: Processing comma-separated value for topic '{topic}': {value}")
            _LOGGER.debug(f"StateParser: Is cell data: {is_cell_data}")
            
            if is_cell_data:
                # For cell data, return the raw comma-separated string for processing by sensor entities
                _LOGGER.debug(f"StateParser: Returning raw cell data: {value}")
                return value
            
            try:
                parts_str = [s.strip() for s in value.split(",") if s.strip()]

                if not parts_str:
                    # If all parts were empty after splitting,
                    # raise ValueError to fall through to 'pass'
                    # This will then correctly result in None for a numeric sensor.
                    raise ValueError("No valid numeric parts found in comma-separated value")

                parts = [float(p) for p in parts_str]
                if parts:
                    # Calculate and return statistics
                    avg_value = sum(parts) / len(parts)
                    # Return the average as the main value, rounded to 6 decimal places for better precision
                    result = round(avg_value, 6)

                    # Additional validation for power metrics
                    if device_class == SensorDeviceClass.POWER:
                        result = StateParser._validate_power_value(result, topic)

                    return result
            except (ValueError, TypeError):
                # If any part can't be converted to float, or cleaning fails to produce valid parts
                pass # Fall through to other parsing methods or return None

        # Try parsing as JSON first
        try:
            json_val = json.loads(value)

            # Handle special JSON values
            if StateParser.is_special_state_value(json_val):
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
                        # Try to preserve integer type when possible
                        if "." not in json_val.strip():
                            return int(json_val)
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
                # Check if it's a float first (contains a decimal point)
                if isinstance(value, str) and "." in value:
                    return float(value)
                # Try to parse as integer first to preserve integer type
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

    @staticmethod
    def _is_cell_data_topic(topic: str) -> bool:
        """Check if this topic contains cell data that should not be averaged."""
        if not topic:
            return False
            
        topic_lower = topic.lower()
        
        # Known cell data patterns - these should preserve individual values
        cell_patterns = [
            # Battery cell data (both dot and slash notation)
            "v.b.c.voltage",
            "v.b.c.temp", 
            "v.b.c.temp.alert",
            "v.b.c.voltage.alert",
            "v.b.c.temp.dev.max",
            "v.b.c.temp.max",
            "v.b.c.temp.min", 
            "v.b.c.voltage.dev.max",
            "v.b.c.voltage.max",
            "v.b.c.voltage.min",
            "v/b/c/voltage",
            "v/b/c/temp",
            # Vehicle-specific cell data (both dot and slash notation)
            "xvu.b.c.soh",
            "xvu.b.hist.soh.mod.",
            "xvu/b/c/voltage",
            "xvu/b/c/temp",
            "xvu/b/c/soh",
            # Tire data
            "v.t.pressure",
            "v.t.temp",
            "v.t.health",
            "v.t.alert",
            "v.t.diff",
            "v.t.emgcy",
            "v/t/pressure",
            "v/t/temp",
            "v/t/health",
            "v/t/alert",
            "v/t/diff",
            "v/t/emgcy",
            # Any metric ending with these patterns
            "/cell/",
            "/cells/",
        ]
        
        # Check if topic matches any cell data pattern
        for pattern in cell_patterns:
            if pattern in topic_lower:
                return True
                
        return False

    @staticmethod
    def _validate_power_value(value: float, topic: str = "") -> float:
        """Validate and correct power values based on common issues."""
        try:
            # Check for common power value issues

            # 1. Values that are likely in milliwatts but should be watts
            if value > 100000:  # > 100kW, probably milliwatts
                _LOGGER.debug(f"Converting suspected milliwatts to watts for topic {topic}: {value} -> {value/1000}")
                return round(value / 1000, 3)

            # 2. Negative power values for charging should be positive
            if "charg" in topic.lower() and value < 0:
                _LOGGER.debug(f"Converting negative charging power to positive for topic {topic}: {value} -> {abs(value)}")
                return abs(value)

            # 3. Very small values that might be in wrong units
            if 0 < value < 0.001:  # Very small, might be kW instead of W
                _LOGGER.debug(f"Converting suspected kW to watts for topic {topic}: {value} -> {value*1000}")
                return round(value * 1000, 3)

            return value

        except Exception as ex:
            _LOGGER.exception(f"Error validating power value {value} for topic {topic}: {ex}")
            return value
