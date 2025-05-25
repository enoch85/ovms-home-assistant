"""OVMS sensor state parsers."""
import json
import logging
import re
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.util import dt as dt_util

from ..const import LOGGER_NAME, MAX_STATE_LENGTH, truncate_state_value
from .duration_formatter import parse_duration

_LOGGER = logging.getLogger(LOGGER_NAME)

# List of device classes that should have numeric values
NUMERIC_DEVICE_CLASSES = [
    SensorDeviceClass.BATTERY,
    SensorDeviceClass.CURRENT,
    SensorDeviceClass.ENERGY,
    SensorDeviceClass.HUMIDITY,
    SensorDeviceClass.POWER,
    SensorDeviceClass.PRESSURE,
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

def parse_comma_separated_values(value: str, entity_name: str = "", is_cell_sensor: bool = False, 
                        stat_type: str = "cell", device_class: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """Parse comma-separated or semicolon-separated values into a dictionary with statistics."""
    
    # This function is often used for attributes of sensors that parse array-like strings.
    # The is_cell_sensor flag can determine if it proceeds, or it can be made more general.
    # For now, respecting the existing is_cell_sensor check:
    if not is_cell_sensor and device_class != SensorDeviceClass.PRESSURE: # Modified condition
        # If this function is intended *only* for cell sensors or pressure sensors, this check is appropriate.
        _LOGGER.debug(
            "Skipping parse_comma_separated_values as it's not a cell sensor or pressure sensor for entity: %s", 
            entity_name
        )
        return None

    result = {}
    try:
        original_input_value = value # Preserve the original input for logging or attributes

        # Determine the separator
        separator = ";" if ";" in original_input_value else ","
        
        string_to_parse_parts_from = original_input_value
        unit_suffix = ""
        
        # Detect and strip known pressure unit suffixes
        pressure_units = ["psi", "kpa", "bar"] # Ensure this list is consistent or centrally managed
        for unit in pressure_units:
            # Case-insensitive check for suffix
            if string_to_parse_parts_from.lower().endswith(unit.lower()):
                # Preserve original casing of the unit if needed, or stick to lower
                unit_suffix = string_to_parse_parts_from[-len(unit):].lower() 
                string_to_parse_parts_from = string_to_parse_parts_from[:-len(unit)].strip()
                _LOGGER.debug("Detected unit \'%s\', remaining string for parsing: \'%s\'", unit_suffix, string_to_parse_parts_from)
                break
        
        result["raw_values_string"] = string_to_parse_parts_from 

        _LOGGER.debug(
            "In parse_comma_separated_values for '%s': processing numeric string '%s' with separator '%s', detected unit_suffix '%s'", 
            entity_name, string_to_parse_parts_from, separator, unit_suffix
        )
        
        parsed_numeric_parts = []
        for part_str in string_to_parse_parts_from.split(separator):
            stripped_part = part_str.strip()
            if stripped_part:
                try:
                    parsed_numeric_parts.append(float(stripped_part))
                except (ValueError, TypeError):
                    _LOGGER.warning(
                        "Could not parse part '%s' as float in value '%s' for entity '%s'. Skipping this part.",
                        stripped_part, original_input_value, entity_name
                    )
            
        if not parsed_numeric_parts:
            _LOGGER.warning(
                "No numeric parts could be successfully parsed from '%s' for entity '%s'.", 
                string_to_parse_parts_from, entity_name
            )
            return None

        _LOGGER.debug(
            "In parse_comma_separated_values for '%s': successfully parsed numeric parts: %s", 
            entity_name, parsed_numeric_parts
        )

        # Store the detected unit suffix in the result.
        # The parsed_numeric_parts are in this unit.
        result["detected_unit"] = unit_suffix if unit_suffix else None # Store None if no unit detected

        # Populate result dictionary with statistics and individual values
        result[f"{stat_type}_values"] = parsed_numeric_parts
        result["count"] = len(parsed_numeric_parts)
        
        if parsed_numeric_parts:
            current_values = parsed_numeric_parts # These are in the detected unit
            
            result["mean"] = sum(current_values) / len(current_values)
            result["median"] = calculate_median(current_values)
            result["min"] = min(current_values)
            result["max"] = max(current_values)

            for i, val in enumerate(current_values):
                result[f"{stat_type}_{i+1}"] = val
            
            # The main "value" of this parsed structure is the mean, in the detected unit.
            result["value"] = round(result["mean"], 4) 
        else:
            result["value"] = None 

        _LOGGER.debug("parse_comma_separated_values result for %s: %s", entity_name, result)
        return result

    except Exception as e:
        _LOGGER.error(
            "Unexpected error in parse_comma_separated_values for entity '%s', value '%s': %s", 
            entity_name, value, e, exc_info=True
        )
        return None

def parse_value(value: Any, device_class: Optional[Any] = None, state_class: Optional[Any] = None,
                is_cell_sensor: bool = False, entity_name: str = "") -> Any: # Added entity_name
    """Parse the value from the payload."""
    
    # If this is a pressure sensor and the value is a string, it might be a comma-separated list
    if device_class == SensorDeviceClass.PRESSURE and isinstance(value, str) and ("," in value or ";" in value):
        _LOGGER.debug("Attempting to parse '%s' as comma-separated pressure value for entity '%s'", value, entity_name)
        parsed_pressure_data = parse_comma_separated_values(
            value, 
            entity_name=entity_name, 
            is_cell_sensor=True, 
            stat_type="pressure", 
            device_class=device_class
        )
        if parsed_pressure_data and "value" in parsed_pressure_data:
            _LOGGER.debug("Parsed pressure data for %s: %s. Returning mean value: %s", entity_name, parsed_pressure_data, parsed_pressure_data["value"])
            return parsed_pressure_data 
        else:
            _LOGGER.warning("Could not parse comma-separated pressure value '%s' for entity '%s'. Falling back.", value, entity_name)
            # Fallback to standard parsing

    # Handle timestamp device class specifically
    if device_class == SensorDeviceClass.TIMESTAMP:
        if isinstance(value, (int, float)):
            try:
                # Attempt to parse as Unix timestamp (seconds)
                # Clamp to a reasonable date range to avoid issues with very small/large numbers
                if datetime(1980, 1, 1).timestamp() < value < datetime(2038, 1, 19).timestamp(): # Typical 32-bit Unix time range
                    dt_obj = datetime.fromtimestamp(value, tz=dt_util.UTC)
                    _LOGGER.debug("Parsed numeric value '%s' as Unix timestamp to %s for entity '%s'", value, dt_obj.isoformat(), entity_name)
                    return dt_obj
                else:
                    _LOGGER.warning("Numeric value '%s' for timestamp entity '%s' is out of expected Unix timestamp range. Returning current time.", value, entity_name)
                    return dt_util.now().astimezone(dt_util.UTC)
            except Exception as e:
                _LOGGER.error("Error parsing numeric value '%s' as Unix timestamp for entity '%s': %s. Returning current time.", value, entity_name, e)
                return dt_util.now().astimezone(dt_util.UTC)
        elif isinstance(value, str):
            try:
                stripped_value = value.strip()
                # Attempt 1: Home Assistant's built-in datetime parser first
                parsed = dt_util.parse_datetime(stripped_value)
                if parsed:
                    if parsed.tzinfo is None:
                        _LOGGER.debug("dt_util.parse_datetime for '%s' (stripped) returned naive datetime. Interpreting as local and converting to UTC.", stripped_value)
                        return dt_util.as_local(parsed).astimezone(dt_util.UTC)
                    return parsed.astimezone(dt_util.UTC)

                # Attempt 2: Custom regex parsing if dt_util.parse_datetime fails
                match = re.match(r'(\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2})\\s*([A-Z]{3,5})?', stripped_value)
                if match:
                    dt_str = match.group(1)
                    tz_abbr = match.group(2)
                    try:
                        dt_naive = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
                        if tz_abbr == "UTC":
                            return dt_naive.replace(tzinfo=dt_util.UTC)
                        elif tz_abbr == "CEST":
                            dt_utc = dt_naive - timedelta(hours=2)
                            return dt_utc.replace(tzinfo=dt_util.UTC)
                        else:
                            _LOGGER.debug(
                                "Timestamp '%s' (stripped) for entity '%s' - TZ part '%s' not explicitly handled or missing. Interpreting as local and converting to UTC.",
                                stripped_value, entity_name, tz_abbr
                            )
                            return dt_util.as_local(dt_naive).astimezone(dt_util.UTC)
                    except ValueError:
                        _LOGGER.warning(
                            "Could not parse extracted datetime string '%s' from value '%s' for entity '%s'.",
                            dt_str, stripped_value, entity_name
                        )
                
                _LOGGER.warning(
                    "Could not parse timestamp string '%s' (stripped value: '%s') for entity '%s'. Returning current time.",
                    value, stripped_value, entity_name
                )
                return dt_util.now().astimezone(dt_util.UTC)
            except Exception as e:
                _LOGGER.error("Error parsing timestamp string '%s' for entity '%s': %s. Returning current time.", value, entity_name, e)
                return dt_util.now().astimezone(dt_util.UTC)
        else:
            # Value is not a string, int, or float for a timestamp sensor
            _LOGGER.warning("Timestamp entity '%s' received value '%s' of unexpected type %s. Returning current time.", entity_name, value, type(value))
            return dt_util.now().astimezone(dt_util.UTC)

    # For duration sensors, use our dedicated parser
    if device_class == SensorDeviceClass.DURATION:
        parsed_duration = parse_duration(value)
        if parsed_duration is not None:
            return parsed_duration
        _LOGGER.warning("Could not parse duration string '%s' for entity '%s'. Falling back.", value, entity_name)
        # If parsing fails, continue with standard processing

    # Handle special state values for numeric sensors
    if requires_numeric_value(device_class, state_class) and is_special_state_value(value):
        _LOGGER.debug("Value '%s' for entity '%s' is a special state value. Returning None.", value, entity_name)
        return None

    # Special handling for yes/no values in numeric sensors
    if requires_numeric_value(device_class, state_class) and isinstance(value, str):
        lower_value = value.lower()
        if lower_value in ["no", "off", "false", "disabled"]:
            _LOGGER.debug("Converting '%s' to 0 for entity '%s'", value, entity_name)
            return 0
        if lower_value in ["yes", "on", "true", "enabled"]:
            _LOGGER.debug("Converting '%s' to 1 for entity '%s'", value, entity_name)
            return 1
    
    # This specific block for "is_cell_sensor and isinstance(value, str) and "," in value:"
    # might be redundant if SensorDeviceClass.PRESSURE is handled above and cell sensors
    # also use SensorDeviceClass.PRESSURE or another class that gets routed to parse_comma_separated_values.
    # If cell sensors are distinct and need this specific simple mean, it can stay.
    # Otherwise, it might lead to double processing or conflicting logic.
    # For now, assuming it might be for a different kind of comma-separated value not covered by the pressure logic.
    if is_cell_sensor and isinstance(value, str) and ("," in value or ";" in value) and device_class != SensorDeviceClass.PRESSURE:
        _LOGGER.debug("Attempting to parse '%s' as comma-separated cell value for entity '%s'", value, entity_name)
        try:
            separator = ";" if ";" in value else ","
            values = [float(part.strip()) for part in value.split(separator) if part.strip()]
            if values:
                mean_val = round(sum(values) / len(values), 4)
                _LOGGER.debug("Parsed cell values for %s: %s. Returning mean: %s", entity_name, values, mean_val)
                return mean_val
            else:
                _LOGGER.warning("No numeric parts in cell value '%s' for entity '%s'", value, entity_name)
        except (ValueError, TypeError):
            _LOGGER.warning("Could not parse comma-separated cell value '%s' for entity '%s'. Falling back.", value, entity_name)
            pass # Fall through to JSON/direct parsing

    # Generic handler for comma-separated numeric values for other numeric sensors
    if requires_numeric_value(device_class, state_class) and \
       isinstance(value, str) and \
       ("," in value or ";" in value):
        # This block is reached if the value is a list-like string for a numeric sensor
        # and was not handled by the more specific pressure or cell-sensor comma list handlers.
        _LOGGER.debug("Attempting to parse '%s' as generic comma-separated numeric value for entity '%s'", value, entity_name)
        try:
            separator = ";" if ";" in value else ","
            parts = [p.strip() for p in value.split(separator) if p.strip()]
            # Attempt to convert all parts to float
            numeric_values = [float(part) for part in parts]
            
            if numeric_values: # Ensure we have some numbers
                avg_value = sum(numeric_values) / len(numeric_values)
                _LOGGER.debug("Parsed generic list for %s: %s. Returning mean: %s", entity_name, numeric_values, round(avg_value, 4))
                return round(avg_value, 4)
            else:
                _LOGGER.warning("No valid numeric parts found in generic list value '%s' for entity '%s'", value, entity_name)
                # Fall through to subsequent parsing attempts
        except (ValueError, TypeError):
            _LOGGER.warning("Could not parse generic comma-separated list '%s' for entity '%s'. Falling back.", value, entity_name)
            # Fall through to subsequent parsing attempts

    # Try parsing as JSON first
    try:
        json_val = json.loads(value) if isinstance(value, str) else value

        if is_special_state_value(json_val):
            _LOGGER.debug("JSON value '%s' for entity '%s' is special. Returning None.", json_val, entity_name)
            return None

        if isinstance(json_val, dict):
            result = None
            if "value" in json_val:
                result = json_val["value"]
            elif "state" in json_val:
                result = json_val["state"]
            else:
                for key, val in json_val.items():
                    if isinstance(val, (int, float)):
                        result = val
                        break
            
            if is_special_state_value(result):
                _LOGGER.debug("Extracted dict value '%s' for entity '%s' is special. Returning None.", result, entity_name)
                return None

            if result is not None:
                _LOGGER.debug("Extracted value from JSON dict for %s: %s", entity_name, result)
                return result

            if requires_numeric_value(device_class, state_class):
                _LOGGER.warning("Could not extract numeric value from JSON dict for %s: %s. Returning None.", entity_name, json_val)
                return None
            _LOGGER.debug("Returning string representation of JSON dict for %s: %s", entity_name, str(json_val))
            return truncate_state_value(str(json_val))

        if isinstance(json_val, (int, float)):
            _LOGGER.debug("JSON value for %s is numeric: %s", entity_name, json_val)
            return json_val

        if isinstance(json_val, str):
            if is_special_state_value(json_val):
                _LOGGER.debug("JSON string value '%s' for entity '%s' is special. Returning None.", json_val, entity_name)
                return None
            if requires_numeric_value(device_class, state_class):
                try:
                    num_val = float(json_val)
                    _LOGGER.debug("Converted JSON string '%s' to float %s for entity '%s'", json_val, num_val, entity_name)
                    return num_val
                except (ValueError, TypeError):
                    _LOGGER.warning("Could not convert JSON string '%s' to float for entity '%s'. Returning None.", json_val, entity_name)
                    return None
            _LOGGER.debug("Returning JSON string value for %s: %s", entity_name, json_val)
            return truncate_state_value(json_val)

        if isinstance(json_val, bool):
            if requires_numeric_value(device_class, state_class):
                val = 1 if json_val else 0
                _LOGGER.debug("Converted JSON bool %s to %s for entity '%s'", json_val, val, entity_name)
                return val
            _LOGGER.debug("Returning JSON bool value for %s: %s", entity_name, json_val)
            return json_val

        if requires_numeric_value(device_class, state_class):
            _LOGGER.warning("JSON value for %s is of unhandled type %s and numeric is required. Returning None.", entity_name, type(json_val))
            return None
        _LOGGER.debug("Returning string representation of JSON value for %s: %s", entity_name, str(json_val))
        return truncate_state_value(str(json_val))

    except (ValueError, json.JSONDecodeError): # Added TypeError to catch non-string inputs to json.loads
        _LOGGER.debug("Value '%s' for entity '%s' is not valid JSON. Trying direct numeric conversion.", value, entity_name)
        try:
            if isinstance(value, (int, float)): # Already a number
                 _LOGGER.debug("Value for %s is already numeric: %s", entity_name, value)
                 return value
            if isinstance(value, str):
                # Check if it's a float
                if "." in value:
                    num_val = float(value)
                    _LOGGER.debug("Converted string '%s' to float %s for entity '%s'", value, num_val, entity_name)
                    return num_val
                # Check if it's an int
                num_val = int(value)
                _LOGGER.debug("Converted string '%s' to int %s for entity '%s'", value, num_val, entity_name)
                return num_val
            # If it's not a string, int, or float at this point, and numeric is required, it's an issue.
            if requires_numeric_value(device_class, state_class):
                _LOGGER.warning("Value '%s' (type %s) for entity '%s' could not be converted to numeric. Returning None.", value, type(value), entity_name)
                return None
            # Otherwise return as is, truncated
            _LOGGER.debug("Value for %s is not numeric, returning as truncated string: %s", entity_name, value)
            return truncate_state_value(str(value))

        except (ValueError, TypeError):
            _LOGGER.warning("Could not convert value '%s' to numeric for entity '%s'. Returning None if numeric, else original (truncated).", value, entity_name)
            if requires_numeric_value(device_class, state_class):
                return None
            return truncate_state_value(str(value)) # Ensure it's a string before returning

def process_json_payload(payload: str, attributes: Dict[str, Any], entity_name: str = "",
                        is_cell_sensor: bool = False, stat_type: str = "cell") -> Dict[str, Any]:
    """Process JSON payload to extract additional attributes."""
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
