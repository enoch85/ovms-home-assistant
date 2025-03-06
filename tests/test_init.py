"""Tests for OVMS integration."""
import pytest
from unittest.mock import patch, MagicMock
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from custom_components.ovms.const import DOMAIN

async def test_setup_entry(hass: HomeAssistant):
    """Test setting up the OVMS integration."""
    # Mock the MQTT client setup
    mqtt_client = MagicMock()
    mqtt_client.async_setup.return_value = True
    
    with patch(
        "custom_components.ovms.mqtt.OVMSMQTTClient",
        return_value=mqtt_client,
    ):
        # Create a mock config entry
        entry = MagicMock()
        entry.data = {
            "host": "localhost",
            "port": 1883,
            "username": "test",
            "password": "test",
            "vehicle_id": "test_vehicle",
            "topic_prefix": "ovms",
            "topic_structure": "{prefix}/{mqtt_username}/{vehicle_id}",
            "mqtt_username": "test",
        }
        entry.entry_id = "test_entry_id"
        
        # Test the setup
        from custom_components.ovms import async_setup_entry
        
        assert await async_setup_entry(hass, entry)
        assert hass.data[DOMAIN][entry.entry_id]["mqtt_client"] == mqtt_client
        mqtt_client.async_setup.assert_called_once()
