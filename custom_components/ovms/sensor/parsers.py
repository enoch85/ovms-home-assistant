"""OVMS sensor state parsers."""

import json
import logging
import re
from typing import Any, Dict, List, Optional
from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.util import dt as dt_util

from ..const import LOGGER_NAME, MAX_STATE_LENGTH, truncate_state_value
from ..metrics.common.tire import TIRE_POSITIONS
from .duration_formatter import parse_duration

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


def is_tire_sensor(device_class: Any = None, category: Optional[str] = None) -> bool:
    """Check if this is a tire sensor based on device class and category."""
    # Check if device class indicates tire data (pressure or temperature)
    if device_class in [SensorDeviceClass.PRESSURE, SensorDeviceClass.TEMPERATURE]:
        # For pressure sensors, assume tire if device class is pressure
        if device_class == SensorDeviceClass.PRESSURE:
            return True
        # For temperature sensors, check if category indicates tire
        if device_class == SensorDeviceClass.TEMPERATURE and category == "tire":
            return True
    return False


def requires_numeric_value(device_class: Any, state_class: Any) -> bool:
    """Check if this sensor requires a numeric value based on its device class."""
    return device_class in NUMERIC_DEVICE_CLASSES or state_class in [
        SensorStateClass.MEASUREMENT,
        SensorStateClass.TOTAL,
        SensorStateClass.TOTAL_INCREASING,
    ]


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
        return (sorted_values[n // 2 - 1] + sorted_values[n // 2]) / 2
    return sorted_values[n // 2]


def parse_comma_separated_values(
    value: str,
    entity_name: str = "",
    is_cell_sensor: bool = False,
    stat_type: str = "cell",
) -> Optional[Dict[str, Any]]:
    """Parse comma-separated values into a dictionary with statistics."""
    # Always attempt to parse if it looks like a comma-separated string,
    # is_cell_sensor will determine if we create individual attributes.
    # The initial cleaning of the value string (e.g. removing "kPa")
    # is now expected to happen in StateParser.parse_value before this function is called.

    result = {}
    try:
        # Value is assumed to be cleaned (no units) by StateParser at this point.
        parts_str = [s.strip() for s in value.split(",") if s.strip()]
        if not parts_str:
            return None  # No valid parts

        parts = [float(p) for p in parts_str]

        if not parts:
            return None

        # Store the array in attributes - use only one consistent naming
        result[f"{stat_type}_values"] = parts
        result["count"] = len(parts)

        # Calculate and store statistics
        result["median"] = calculate_median(parts)
        result["mean"] = sum(parts) / len(parts)
        result["min"] = min(parts)
        result["max"] = max(parts)

        # If it's a cell sensor, store individual values with appropriate names
        # These will become attributes of the main sensor.
        if is_cell_sensor:
            for i, val in enumerate(parts):
                # Check if this is a tire sensor by stat_type or if it's specifically tire data
                is_tire_data = (
                    stat_type in ["tire", "pressure"] and stat_type != "cell" and i < 4
                )
                if is_tire_data:
                    # Use tire position labels for tire sensors (up to 4 tires)
                    position_name, position_code = TIRE_POSITIONS[i]
                    result[f"{stat_type}_{position_code}"] = val
                else:
                    # Use generic naming for other sensors or additional values beyond 4 tires
                    result[f"cell_{i+1}"] = val

        # The main 'value' of the sensor will be the median for cell sensors
        # This matches the behavior shown in the working cell voltage display
        result["value"] = round(result["median"], 4)
        _LOGGER.debug(
            f"parse_comma_separated_values: Processed '{value}' -> median: {result['median']}, final value: {result['value']}"
        )
        return result
    except (ValueError, TypeError):
        _LOGGER.warning(
            f"Could not parse comma-separated values for {entity_name}: '{value}'"
        )
        pass
    return None


def parse_value(
    value: Any,
    device_class: Optional[Any] = None,
    state_class: Optional[Any] = None,
    is_cell_sensor: bool = False,
) -> Any:
    """Parse the value from the payload."""
    # Handle timestamp device class specifically
    if device_class == SensorDeviceClass.TIMESTAMP and isinstance(value, str):
        try:
            # Try Home Assistant's built-in datetime parser first
            parsed = dt_util.parse_datetime(value)
            if parsed:
                return parsed

            # For OVMS timestamp format, extract just the datetime part
            import datetime
            import re

            # Match format "2025-03-25 17:42:57 TIMEZONE" and extract datetime part
            match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", value)
            if match:
                dt_str = match.group(1)
                # Create a datetime object without timezone info
                dt_obj = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                # Home Assistant requires tzinfo, but we'll use local time zone
                return dt_util.as_local(dt_obj)

            # Return current time if we can't parse it instead of failing
            return dt_util.now()
        except Exception:
            # Return current time on parse failure instead of None
            return dt_util.now()

    # For duration sensors, use our dedicated parser
    if device_class == SensorDeviceClass.DURATION:
        parsed_duration = parse_duration(value)
        if parsed_duration is not None:
            return parsed_duration
        # If parsing fails, continue with standard processing

    # Handle special state values for numeric sensors
    if requires_numeric_value(device_class, state_class) and is_special_state_value(
        value
    ):
        return None

    # Special handling for yes/no values in numeric sensors
    if requires_numeric_value(device_class, state_class) and isinstance(value, str):
        # Convert common boolean strings to numeric values
        if value.lower() in ["no", "off", "false", "disabled"]:
            return 0
        if value.lower() in ["yes", "on", "true", "enabled"]:
            return 1

        # Check if this is a comma-separated list of numbers for a cell sensor
        if isinstance(value, str) and "," in value and is_cell_sensor:
            # For cell sensors, the StateParser should have already detected this as cell data
            # and returned the raw comma-separated string. Now we process it to get median/attributes.
            # This should ideally be harmonized with StateParser to avoid any duplication.
            stat_type = "tire" if is_tire_sensor(device_class) else "cell"
            parsed_data = parse_comma_separated_values(
                value, "", is_cell_sensor, stat_type
            )
            if parsed_data and "value" in parsed_data:
                # The main sensor state will be the median value from parse_comma_separated_values
                return parsed_data["value"]
            else:
                # Fallback if parsing failed
                return None

    # Try parsing as JSON first
    try:
        json_val = json.loads(value) if isinstance(value, str) else value

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

            # If we have a result, return it
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
                    # Try to preserve integer type when possible
                    if "." not in json_val.strip():
                        return int(json_val)
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
            # Otherwise return as is
            return value


def process_json_payload(
    payload: str,
    attributes: Dict[str, Any],
    entity_name: str = "",
    is_cell_sensor: bool = False,
    stat_type: str = "cell",
) -> Dict[str, Any]:
    """Process JSON payload to extract additional attributes."""
    updated_attributes = attributes.copy()

    try:
        # If it's a cell sensor and the payload is a comma-separated string,
        # parse it for individual values and statistics to add as attributes.
        if is_cell_sensor and isinstance(payload, str) and "," in payload:
            # The payload string should be pre-cleaned by StateParser by this point
            stat_type = (
                "tire"
                if is_tire_sensor(
                    attributes.get("device_class"), attributes.get("category")
                )
                else "cell"
            )
            parsed_cells = parse_comma_separated_values(
                payload, entity_name, is_cell_sensor, stat_type
            )
            if parsed_cells:
                for key, val in parsed_cells.items():
                    if (
                        key != "value"
                    ):  # 'value' is the main state, others are attributes
                        updated_attributes[key] = val

        # If not a cell sensor or payload is not a comma-separated string, try JSON parsing for attributes.
        # This 'else' ensures we don't try to JSON parse the comma-separated string itself if it was handled above.
        else:
            try:
                json_data = json.loads(payload) if isinstance(payload, str) else payload
                if isinstance(json_data, dict):
                    # Add all fields as attributes
                    for key, value in json_data.items():
                        if (
                            key not in ["value", "state", "data"]
                            and key not in updated_attributes
                        ):
                            updated_attributes[key] = value

                    # If there's a timestamp in the JSON, use it
                    if "timestamp" in json_data:
                        updated_attributes["device_timestamp"] = json_data["timestamp"]

                    # If there's a unit in the JSON, use it for native unit
                    if (
                        "unit" in json_data
                        and "unit_of_measurement" not in updated_attributes
                    ):
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
                        updated_attributes["mean"] = sum(numeric_values) / len(
                            numeric_values
                        )
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
