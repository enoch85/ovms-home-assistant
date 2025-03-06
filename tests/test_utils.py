"""Tests for the utils module."""
from unittest.mock import patch
import json
from custom_components.ovms.utils import (
    convert_temperature,
    convert_distance,
    parse_numeric_value,
    extract_value_from_json,
    parse_gps_coordinates,
)
from homeassistant.const import (
    TEMP_CELSIUS, TEMP_FAHRENHEIT,  # Legacy imports for compatibility
    LENGTH_KILOMETERS, LENGTH_MILES,
)

# For newer Home Assistant versions
try:
    from homeassistant.const import UnitOfTemperature, UnitOfLength, UnitOfSpeed
except ImportError:
    # Create compatibility classes for testing
    class UnitOfTemperature:
        CELSIUS = TEMP_CELSIUS
        FAHRENHEIT = TEMP_FAHRENHEIT
    
    class UnitOfLength:
        KILOMETERS = LENGTH_KILOMETERS
        MILES = LENGTH_MILES
    
    class UnitOfSpeed:
        KILOMETERS_PER_HOUR = "km/h"
        MILES_PER_HOUR = "mph"

def test_convert_temperature():
    """Test temperature conversion."""
    assert convert_temperature(20, UnitOfTemperature.CELSIUS) == 20
    assert convert_temperature(20, UnitOfTemperature.FAHRENHEIT) == 68
    
def test_convert_distance():
    """Test distance conversion."""
    assert convert_distance(10, UnitOfLength.KILOMETERS) == 10
    assert round(convert_distance(10, UnitOfLength.MILES), 2) == 6.21

def test_parse_numeric_value():
    """Test parsing numeric values."""
    assert parse_numeric_value(10) == 10.0
    assert parse_numeric_value("10") == 10.0
    assert parse_numeric_value("10.5") == 10.5
    assert parse_numeric_value("10.5 km") == 10.5
    assert parse_numeric_value(None) is None
    assert parse_numeric_value("not a number") is None

def test_extract_value_from_json():
    """Test extracting values from JSON."""
    json_str = json.dumps({"battery": {"soc": 75}})
    assert extract_value_from_json(json_str) == {"battery": {"soc": 75}}
    assert extract_value_from_json(json_str, "battery.soc") == 75
    assert extract_value_from_json(json_str, "battery.invalid") is None
    assert extract_value_from_json("not json") is None

def test_parse_gps_coordinates():
    """Test parsing GPS coordinates."""
    # Test JSON format
    json_str = json.dumps({"lat": 45.0, "lon": -120.0})
    lat, lon = parse_gps_coordinates(json_str)
    assert lat == 45.0
    assert lon == -120.0
    
    # Test CSV format
    lat, lon = parse_gps_coordinates("45.0, -120.0")
    assert lat == 45.0
    assert lon == -120.0
    
    # Test invalid input
    lat, lon = parse_gps_coordinates("invalid")
    assert lat is None
    assert lon is None
