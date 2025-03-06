"""Tests for the OVMS MQTT client."""
import asyncio
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_USERNAME, CONF_PASSWORD, CONF_PROTOCOL

from custom_components.ovms.mqtt import OVMSMQTTClient
from custom_components.ovms.const import (
    CONF_TOPIC_PREFIX,
    CONF_MQTT_USERNAME,
    CONF_VEHICLE_ID,
    CONF_TOPIC_STRUCTURE,
    CONF_QOS,
    DEFAULT_TOPIC_STRUCTURE
)


@pytest.fixture
def mock_mqtt_client():
    """Fixture to create a mock MQTT client."""
    with patch("custom_components.ovms.mqtt.mqtt.Client") as mock_mqtt:
        mock_client = MagicMock()
        mock_mqtt.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_hass():
    """Fixture to create a mock hass object."""
    hass = MagicMock(spec=HomeAssistant)
    hass.async_add_executor_job = AsyncMock()
    hass.loop = asyncio.get_event_loop()
    return hass


@pytest.fixture
def test_config():
    """Fixture to create a test configuration."""
    return {
        CONF_HOST: "test-broker.example.com",
        CONF_PORT: 1883,
        CONF_PROTOCOL: "mqtt",
        CONF_USERNAME: "test_user",
        CONF_PASSWORD: "test_password",
        CONF_TOPIC_PREFIX: "ovms",
        CONF_MQTT_USERNAME: "mqtt_user",
        CONF_VEHICLE_ID: "test_vehicle",
        CONF_TOPIC_STRUCTURE: DEFAULT_TOPIC_STRUCTURE,
        CONF_QOS: 1
    }


class TestOVMSMQTTClient:
    """Tests for the OVMSMQTTClient class."""

    async def test_init(self, mock_hass, test_config):
        """Test initializing the MQTT client."""
        client = OVMSMQTTClient(mock_hass, test_config)
        
        assert client.hass == mock_hass
        assert client.config == test_config
        assert client.client is None
        assert client.connected is False
        assert client.topic_cache == {}
        assert client.discovered_topics == set()
        assert client.entity_registry == {}
        assert client.entity_types == {}
        assert client.structure_prefix is None
        assert client.pending_commands == {}
        assert client.message_count == 0
        assert client.reconnect_count == 0
        assert client.platforms_loaded is False

    async def test_format_structure_prefix(self, mock_hass, test_config):
        """Test formatting the structure prefix."""
        client = OVMSMQTTClient(mock_hass, test_config)
        prefix = client._format_structure_prefix()
        
        expected_prefix = "ovms/mqtt_user/test_vehicle"
        assert prefix == expected_prefix

    async def test_async_setup(self, mock_hass, mock_mqtt_client, test_config):
        """Test setting up the MQTT client."""
        with patch("custom_components.ovms.mqtt.OVMSMQTTClient._async_connect") as mock_connect, \
             patch("custom_components.ovms.mqtt.OVMSMQTTClient._subscribe_topics") as mock_subscribe, \
             patch("custom_components.ovms.mqtt.async_dispatcher_connect") as mock_dispatcher:
            
            mock_connect.return_value = True
            
            client = OVMSMQTTClient(mock_hass, test_config)
            result = await client.async_setup()
            
            assert result is True
            assert client.structure_prefix == "ovms/mqtt_user/test_vehicle"
            assert client.client is not None
            mock_connect.assert_called_once()
            mock_subscribe.assert_called_once()
            mock_dispatcher.assert_called_once()

    async def test_async_setup_fail_connect(self, mock_hass, mock_mqtt_client, test_config):
        """Test setup failing due to connection error."""
        with patch("custom_components.ovms.mqtt.OVMSMQTTClient._async_connect") as mock_connect:
            mock_connect.return_value = False
            
            client = OVMSMQTTClient(mock_hass, test_config)
            result = await client.async_setup()
            
            assert result is False

    async def test_async_send_command(self, mock_hass, mock_mqtt_client, test_config):
        """Test sending a command."""
        client = OVMSMQTTClient(mock_hass, test_config)
        client.client = mock_mqtt_client
        client.connected = True
        client.structure_prefix = "ovms/mqtt_user/test_vehicle"
        
        # Create a fake response handler
        def fake_publish_and_response(topic, payload, qos=0):
            # Simulate a successful publish
            command_id = topic.split("/")[-1]
            # Set the result for the future in pending_commands
            future = client.pending_commands[command_id]["future"]
            future.set_result('{"status": "ok"}')
            
        mock_mqtt_client.publish.side_effect = fake_publish_and_response
        
        # Send a test command
        result = await client.async_send_command("test_command", "test_params", "test123")
        
        assert result["success"] is True
        assert result["command"] == "test_command"
        assert result["parameters"] == "test_params"
        assert result["command_id"] == "test123"
        assert result["response"] == {"status": "ok"}
        mock_mqtt_client.publish.assert_called_once()

    async def test_async_send_command_timeout(self, mock_hass, mock_mqtt_client, test_config):
        """Test sending a command that times out."""
        client = OVMSMQTTClient(mock_hass, test_config)
        client.client = mock_mqtt_client
        client.connected = True
        client.structure_prefix = "ovms/mqtt_user/test_vehicle"
        
        # Create a fake publish that doesn't respond
        def fake_publish_no_response(topic, payload, qos=0):
            # Just publish but don't set any result for the future
            pass
            
        mock_mqtt_client.publish.side_effect = fake_publish_no_response
        
        # Send a test command with a short timeout
        result = await client.async_send_command("test_command", "test_params", "test123", timeout=0.1)
        
        assert result["success"] is False
        assert "timeout" in result["error"].lower()
        assert result["command"] == "test_command"
        assert result["parameters"] == "test_params"
        assert result["command_id"] == "test123"
        mock_mqtt_client.publish.assert_called_once()

    async def test_async_platforms_loaded(self, mock_hass, mock_mqtt_client, test_config):
        """Test handling platforms loaded event."""
        with patch("custom_components.ovms.mqtt.async_dispatcher_send") as mock_dispatcher:
            client = OVMSMQTTClient(mock_hass, test_config)
            
            # Queue some fake entities
            client.entity_queue.append({"name": "test_entity"})
            
            # Test processing when platforms are loaded
            await client._async_platforms_loaded()
            
            assert client.platforms_loaded is True
            assert len(client.entity_queue) == 0
            mock_dispatcher.assert_called_once()

    def test_parse_topic(self, mock_hass, test_config):
        """Test parsing a topic."""
        with patch("custom_components.ovms.mqtt.get_metric_by_path") as mock_get_path, \
             patch("custom_components.ovms.mqtt.get_metric_by_pattern") as mock_get_pattern:
            
            # Configure the mocks
            mock_get_path.return_value = {
                "name": "Battery Level",
                "icon": "mdi:battery",
                "device_class": "battery",
                "category": "battery"
            }
            
            client = OVMSMQTTClient(mock_hass, test_config)
            client.structure_prefix = "ovms/mqtt_user/test_vehicle"
            
            # Test parsing a battery sensor topic
            topic = "ovms/mqtt_user/test_vehicle/metric/v/b/soc"
            entity_type, entity_info = client._parse_topic(topic)
            
            assert entity_type == "sensor"
            assert entity_info["name"] == "metric_v_b_soc"
            assert "Battery Level" in entity_info["friendly_name"]
            assert entity_info["attributes"]["category"] == "battery"
