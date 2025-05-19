"""State parser for OVMS integration."""
import json
import logging
import re
from typing import Any, Dict, List, Optional

from homeassistant.components.sensor import SensorDeviceClass

from ..const import LOGGER_NAME, DOMAIN

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

        # Check for unit suffix like "psi" at the end
        unit_suffix = ""
        value_without_unit = value
        
        # Only process strings
        if isinstance(value, str):
            # Pressure unit suffixes to check for
            pressure_units = ["psi", "kpa", "bar"]
            for unit in pressure_units:
                if value.lower().endswith(unit):
                    unit_suffix = value[-len(unit):].lower()
                    value_without_unit = value[:-len(unit)]
                    break
                
        # Check if this is a separator-based list (comma or semicolon separated) of numbers
        if isinstance(value_without_unit, str) and ("," in value_without_unit or ";" in value_without_unit):
            try:
                # Determine the separator
                separator = ";" if ";" in value_without_unit else ","
                
                # Handling for tire pressure values
                if device_class == SensorDeviceClass.PRESSURE:
                    _LOGGER.debug("Processing tire pressure values for string: '%s'", value_without_unit)
                    
                    parsed_floats = []
                    all_parts_valid = True
                    # Split the string into potential parts, stripping whitespace and removing empty parts
                    potential_parts = [p.strip() for p in value_without_unit.split(separator) if p.strip()]

                    if not potential_parts: # If, after stripping and filtering, there are no parts
                        _LOGGER.debug("No valid parts found after splitting and stripping: '%s'", value_without_unit)
                        all_parts_valid = False # Will cause fall-through
                    else:
                        for part_str in potential_parts:
                            # Each part_str is already stripped and non-empty here
                            try:
                                parsed_floats.append(float(part_str))
                            except (ValueError, TypeError):
                                _LOGGER.debug("Failed to parse '%s' as float in pressure-specific block.", part_str)
                                all_parts_valid = False
                                break # Stop processing if one part is invalid for this specific block
                    
                    if all_parts_valid and parsed_floats: # Ensure all parts were valid and we have some numbers
                        _LOGGER.debug("Successfully parsed all pressure parts: %s from '%s'", parsed_floats, value_without_unit)
                        
                        # Unit conversion if necessary (e.g., psi to kPa)
                        if unit_suffix == "psi": # Already know device_class is PRESSURE
                            from ..utils import convert_pressure
                            from homeassistant.const import UnitOfPressure
                            parsed_floats = [convert_pressure(p, "psi", UnitOfPressure.KPA) for p in parsed_floats]
                            _LOGGER.debug("Converted PSI pressure parts to KPA: %s", parsed_floats)
                        
                        avg_value = sum(parsed_floats) / len(parsed_floats)
                        result = round(avg_value, 4)
                        _LOGGER.debug("Calculated pressure result: %s from parts: %s", result, parsed_floats)
                        return result
                    else:
                        # If not all parts were valid, or no parts were found,
                        # fall through to the generic list parser or other parsing methods.
                        _LOGGER.debug("Falling through from pressure-specific block for: '%s'", value_without_unit)

                # Generic comma/semicolon separated list parsing (fallback or for other device classes)
                _LOGGER.debug("Processing comma/semicolon list (generic fallback): '%s' with device_class: %s", value_without_unit, device_class)
                
                generic_parts_parsed = []
                all_generic_parts_valid = True
                potential_generic_parts = [p.strip() for p in value_without_unit.split(separator) if p.strip()]

                if not potential_generic_parts:
                    all_generic_parts_valid = False
                else:
                    for part_str in potential_generic_parts:
                        try:
                            generic_parts_parsed.append(float(part_str))
                        except (ValueError, TypeError):
                            all_generic_parts_valid = False
                            _LOGGER.debug("Generic list parser failed to parse part '%s' from '%s'", part_str, value_without_unit)
                            break
                
                if all_generic_parts_valid and generic_parts_parsed:
                    _LOGGER.debug("Parsed generic parts: %s from '%s'", generic_parts_parsed, value_without_unit)
                    # Unit conversion for pressure, if applicable and not handled above
                    if unit_suffix == "psi" and device_class == SensorDeviceClass.PRESSURE:
                        from ..utils import convert_pressure
                        from homeassistant.const import UnitOfPressure
                        generic_parts_parsed = [convert_pressure(part, "psi", UnitOfPressure.KPA) for part in generic_parts_parsed]
                        _LOGGER.debug("Converted pressure parts (generic fallback) from psi: %s", generic_parts_parsed)
                    
                    avg_value = sum(generic_parts_parsed) / len(generic_parts_parsed)
                    result = round(avg_value, 4)
                    _LOGGER.debug("Calculated generic list result: %s from parts: %s", result, generic_parts_parsed)
                    return result
                else:
                    _LOGGER.debug("Generic list parsing failed or yielded no parts for: '%s'", value_without_unit)

            except Exception as e: # Catch any unexpected error during list processing
                _LOGGER.debug("Error during comma/semicolon list processing for '%s': %s. Falling through.", value_without_unit, e, exc_info=True)
                # Fall through to other parsing methods
                pass

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
