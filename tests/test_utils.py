"""Tests for the OVMS utility functions."""
import pytest
import json
from unittest.mock import patch

from homeassistant.const import (
    UnitOfTemperature,
    UnitOfLength,
    UnitOfSpeed,
    UnitOfVolume,
)

from custom_components.ovms.utils import (
    convert_temperature,
    convert_distance,
    convert_speed,
    convert_volume,
    get_unit_system,
    clean_topic,
    parse_numeric_value,
    extract_value_from_json,
    safe_float,
    topic_matches_pattern,
    generate_unique_id,
    parse_gps_coordinates,
    format_command_parameters,
)


class TestUnitConversions:
    """Test unit conversion functions."""

    def test_convert_temperature(self):
        """Test temperature conversion."""
        # Test Celsius to Celsius (no change)
        assert convert_temperature(25.0, UnitOfTemperature.CELSIUS) == 25.0
        
        # Test Celsius to Fahrenheit
        assert convert_temperature(0.0, UnitOfTemperature.FAHRENHEIT) == 32.0
        assert convert_temperature(100.0, UnitOfTemperature.FAHRENHEIT) == 212.0
        assert convert_temperature(25.0, UnitOfTemperature.FAHRENHEIT) == 77.0
        
        # Test with unknown unit (should return original)
        assert convert_temperature(25.0, "unknown") == 25.0

    def test_convert_distance(self):
        """Test distance conversion."""
        # Test km to km (no change)
        assert convert_distance(100.0, UnitOfLength.KILOMETERS) == 100.0
        
        # Test km to miles
        assert convert_distance(100.0, UnitOfLength.MILES) == pytest.approx(62.1371)
        assert convert_distance(1.0, UnitOfLength.MILES) == pytest.approx(0.621371)
        
        # Test with unknown unit (should return original)
        assert convert_distance(100.0, "unknown") == 100.0

    def test_convert_speed(self):
        """Test speed conversion."""
        # Test km/h to km/h (no change)
        assert convert_speed(100.0, UnitOfSpeed.KILOMETERS_PER_HOUR) == 100.0
        
        # Test km/h to mph
        assert convert_speed(100.0, UnitOfSpeed.MILES_PER_HOUR) == pytest.approx(62.1371)
        
        # Test with unknown unit (should return original)
        assert convert_speed(100.0, "unknown") == 100.0

    def test_convert_volume(self):
        """Test volume conversion."""
        # Test liters to liters (no change)
        assert convert_volume(10.0, UnitOfVolume.LITERS) == 10.0
        
        # Test liters to gallons
        assert convert_volume(10.0, UnitOfVolume.GALLONS) == pytest.approx(2.64172)
        
        # Test with unknown unit (should return original)
        assert convert_volume(10.0, "unknown") == 10.0

    def test_get_unit_system(self):
        """Test getting unit system."""
        # Test metric system
        metric = get_unit_system(True)
        assert metric["temperature"] == UnitOfTemperature.CELSIUS
        assert metric["distance"] == UnitOfLength.KILOMETERS
        assert metric["speed"] == UnitOfSpeed.KILOMETERS_PER_HOUR
        assert metric["volume"] == UnitOfVolume.LITERS
        
        # Test imperial system
        imperial = get_unit_system(False)
        assert imperial["temperature"] == UnitOfTemperature.FAHRENHEIT
        assert imperial["distance"] == UnitOfLength.MILES
        assert imperial["speed"] == UnitOfSpeed.MILES_PER_HOUR
        assert imperial["volume"] == UnitOfVolume.GALLONS


class TestTopicUtils:
    """Test topic utility functions."""

    def test_clean_topic(self):
        """Test cleaning topic strings."""
        assert clean_topic("test/topic") == "test_topic"
        assert clean_topic("ovms/+/test") == "ovms_any_test"
        assert clean_topic("ovms/#") == "ovms_all"
        assert clean_topic("ovms/user/vehicle/v/b/#") == "ovms_user_vehicle_v_b_all"

    def test_topic_matches_pattern(self):
        """Test pattern matching for topics."""
        # Test exact match
        assert topic_matches_pattern("test/topic", "test/topic") is True
        
        # Test with + wildcard
        assert topic_matches_pattern("test/foo/bar", "test/+/bar") is True
        assert topic_matches_pattern("test/foo/baz", "test/+/bar") is False
        
        # Test with # wildcard
        assert topic_matches_pattern("test/foo/bar", "test/#") is True
        assert topic_matches_pattern("test/foo/bar/baz", "test/foo/#") is True
        assert topic_matches_pattern("other/foo/bar", "test/#") is False
        
        # Test with multiple wildcards
        assert topic_matches_pattern("test/foo/bar/baz", "test/+/+/baz") is True
        assert topic_matches_pattern("test/foo/bar/bam", "test/+/+/baz") is False


class TestValueParsing:
    """Test value parsing utilities."""

    def test_parse_numeric_value(self):
        """Test parsing numeric values."""
        # Test with numbers
        assert parse_numeric_value(42) == 42.0
        assert parse_numeric_value(3.14) == 3.14
        
        # Test with strings
        assert parse_numeric_value("42") == 42.0
        assert parse_numeric_value("3.14") == 3.14
        assert parse_numeric_value("-10.5") == -10.5
        
        # Test with strings containing units
        assert parse_numeric_value("42V") == 42.0
        assert parse_numeric_value("3.14 km") == 3.14
        assert parse_numeric_value("10.5°C") == 10.5
        
        # Test with non-numeric values
        assert parse_numeric_value("text") is None
        assert parse_numeric_value(None) is None
        assert parse_numeric_value("") is None

    def test_extract_value_from_json(self):
        """Test extracting values from JSON."""
        # Test with simple values
        assert extract_value_from_json('42') == 42
        assert extract_value_from_json('"text"') == "text"
        assert extract_value_from_json('true') is True
        
        # Test with objects
        json_obj = '{"value": 42, "unit": "V"}'
        assert extract_value_from_json(json_obj) == {"value": 42, "unit": "V"}
        
        # Test with nested path
        json_obj = '{"battery": {"soc": 75, "voltage": 400}}'
        assert extract_value_from_json(json_obj, "battery.soc") == 75
        assert extract_value_from_json(json_obj, "battery.voltage") == 400
        
        # Test with missing path
        assert extract_value_from_json(json_obj, "battery.current") is None
        assert extract_value_from_json(json_obj, "nonexistent") is None
        
        # Test with invalid JSON
        assert extract_value_from_json("not json") is None

    def test_safe_float(self):
        """Test safe float conversion."""
        # Test with numbers
        assert safe_float(42) == 42.0
        assert safe_float(3.14) == 3.14
        
        # Test with strings
        assert safe_float("42") == 42.0
        assert safe_float("3.14") == 3.14
        
        # Test with invalid inputs
        assert safe_float("text") is None
        assert safe_float(None) is None
        assert safe_float("") is None

    def test_parse_gps_coordinates(self):
        """Test parsing GPS coordinates."""
        # Test with JSON object
        json_coords = '{"latitude": 51.5074, "longitude": -0.1278}'
        lat, lon = parse_gps_coordinates(json_coords)
        assert lat == 51.5074
        assert lon == -0.1278
        
        # Test with different field names
        json_coords = '{"lat": 51.5074, "lng": -0.1278}'
        lat, lon = parse_gps_coordinates(json_coords)
        assert lat == 51.5074
        assert lon == -0.1278
        
        # Test with comma-separated values
        csv_coords = "51.5074, -0.1278"
        lat, lon = parse_gps_coordinates(csv_coords)
        assert lat == 51.5074
        assert lon == -0.1278
        
        # Test with invalid coordinates (out of range)
        invalid_coords = "200.0, 300.0"
        lat, lon = parse_gps_coordinates(invalid_coords)
        assert lat is None
        assert lon is None
        
        # Test with invalid inputs
        assert parse_gps_coordinates("not coordinates") == (None, None)
        assert parse_gps_coordinates(None) == (None, None)


class TestMiscUtils:
    """Test miscellaneous utilities."""

    def test_generate_unique_id(self):
        """Test unique ID generation."""
        # Test with simple components
        assert generate_unique_id(["ovms", "vehicle", "sensor"]) == "ovms_vehicle_sensor"
        
        # Test with empty components
        assert generate_unique_id([]) == "unknown"
        assert generate_unique_id([None, "", None]) == "unknown"
        
        # Test with special characters
        id_with_special = generate_unique_id(["ovms/test", "sensor@123"])
        assert "/" not in id_with_special
        assert "@" not in id_with_special
        
        # Test with very long components (should hash)
        long_comp = "x" * 100
        long_id = generate_unique_id(["ovms", long_comp, "sensor"])
        assert len(long_id) == 32  # MD5 hash length
        assert long_id.isalnum()  # Should be alphanumeric

    def test_format_command_parameters(self):
        """Test formatting command parameters."""
        # Test with string parameters
        assert format_command_parameters("test", "param1 param2") == "test param1 param2"
        
        # Test with empty parameters
        assert format_command_parameters("test", "") == "test"
        assert format_command_parameters("test", None) == "test"
        
        # Test with dict parameters
        params = {"key1": "value1", "key2": "value2"}
        formatted = format_command_parameters("test", params)
        assert formatted == "test key1=value1 key2=value2" or formatted == "test key2=value2 key1=value1"
