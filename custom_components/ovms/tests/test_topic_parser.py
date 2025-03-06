"""Tests for the OVMS topic parser helper."""
import pytest
from unittest.mock import patch, MagicMock

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass

from custom_components.ovms.helpers.topic_parser import OVMSTopicParser


class TestOVMSTopicParser:
    """Tests for the OVMSTopicParser class."""
    
    def test_parse_topic_no_match(self):
        """Test parsing a topic that doesn't match the structure prefix."""
        structure_prefix = "ovms/username/vehicle"
        topic = "wrong/prefix/topic"
        
        entity_type, entity_info = OVMSTopicParser.parse_topic(topic, structure_prefix)
        
        assert entity_type is None
        assert entity_info is None
    
    def test_parse_topic_command_response(self):
        """Test parsing a command/response topic which should be skipped."""
        structure_prefix = "ovms/username/vehicle"
        topic = f"{structure_prefix}/client/rr/command/12345"
        
        entity_type, entity_info = OVMSTopicParser.parse_topic(topic, structure_prefix)
        
        assert entity_type is None
        assert entity_info is None
    
    def test_parse_topic_battery_sensor(self):
        """Test parsing a battery sensor topic."""
        structure_prefix = "ovms/username/vehicle"
        topic = f"{structure_prefix}/metric/v/b/soc"
        
        with patch("custom_components.ovms.helpers.topic_parser.get_metric_by_path") as mock_get_path:
            mock_get_path.return_value = {
                "name": "Battery Level",
                "device_class": SensorDeviceClass.BATTERY,
                "category": "battery",
                "icon": "mdi:battery",
            }
            
            entity_type, entity_info = OVMSTopicParser.parse_topic(topic, structure_prefix)
            
            assert entity_type == "sensor"
            assert entity_info["name"] == "metric_v_b_soc"
            assert entity_info["friendly_name"] == "Battery Level"
            assert entity_info["attributes"]["category"] == "battery"
    
    def test_parse_topic_door_binary_sensor(self):
        """Test parsing a door binary sensor topic."""
        structure_prefix = "ovms/username/vehicle"
        topic = f"{structure_prefix}/metric/v/d/door"
        
        with patch("custom_components.ovms.helpers.topic_parser.get_metric_by_path") as mock_get_path:
            mock_get_path.return_value = {
                "name": "Door",
                "device_class": BinarySensorDeviceClass.DOOR,
                "category": "door",
                "icon": "mdi:car-door",
            }
            
            entity_type, entity_info = OVMSTopicParser.parse_topic(topic, structure_prefix)
            
            assert entity_type == "binary_sensor"
            assert entity_info["name"] == "metric_v_d_door"
            assert entity_info["friendly_name"] == "Door"
            assert entity_info["attributes"]["category"] == "door"
    
    def test_parse_topic_location_tracker(self):
        """Test parsing a location tracker topic."""
        structure_prefix = "ovms/username/vehicle"
        topic = f"{structure_prefix}/metric/v/p/latitude"
        
        with patch("custom_components.ovms.helpers.topic_parser.get_metric_by_path") as mock_get_path:
            # No exact metric match
            mock_get_path.return_value = None
            
            # Setup pattern to detect it's location data
            with patch("custom_components.ovms.helpers.topic_parser.get_metric_by_pattern") as mock_get_pattern:
                mock_get_pattern.return_value = {
                    "name": "Latitude",
                    "category": "location",
                }
                
                entity_type, entity_info = OVMSTopicParser.parse_topic(topic, structure_prefix)
                
                assert entity_type == "device_tracker"
                assert entity_info["name"] == "metric_v_p_latitude"
                assert entity_info["friendly_name"] == "Latitude"
                assert entity_info["attributes"]["category"] == "location"
    
    def test_parse_topic_command_switch(self):
        """Test parsing a command topic that should be a switch."""
        structure_prefix = "ovms/username/vehicle"
        topic = f"{structure_prefix}/command/climate"
        
        entity_type, entity_info = OVMSTopicParser.parse_topic(topic, structure_prefix)
        
        assert entity_type == "switch"
        assert entity_info["name"] == "command_climate"
        assert "climate" in entity_info["friendly_name"].lower()
    
    def test_parse_topic_unknown_but_valid(self):
        """Test parsing a valid topic with no specific matching patterns."""
        structure_prefix = "ovms/username/vehicle"
        topic = f"{structure_prefix}/custom/data"
        
        entity_type, entity_info = OVMSTopicParser.parse_topic(topic, structure_prefix)
        
        assert entity_type == "sensor"  # Default is sensor
        assert entity_info["name"] == "custom_data"
        assert entity_info["attributes"]["category"] == "system"  # Default category
