"""Tests for on-demand metric request feature (OVMS edge firmware).

This module tests the hybrid discovery mechanism that uses on-demand metric
requests for faster discovery on edge/newer firmware while falling back to passive
discovery on stable firmware.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import sys
from pathlib import Path

# Add the custom_components to the path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components"))

from ovms.const import (
    METRIC_REQUEST_TOPIC_TEMPLATE,
    CONFIG_REQUEST_TOPIC_TEMPLATE,
    CONFIG_RESPONSE_TOPIC_TEMPLATE,
    ACTIVE_DISCOVERY_TIMEOUT,
    LEGACY_DISCOVERY_TIMEOUT,
    DEFAULT_TOPIC_STRUCTURE,
    DEFAULT_TOPIC_PREFIX,
)


class TestMetricRequestConstants:
    """Test the new constants added for metric request feature."""

    def test_metric_request_topic_template_format(self):
        """Test that the metric request topic template has correct placeholders."""
        assert "{structure_prefix}" in METRIC_REQUEST_TOPIC_TEMPLATE
        assert "{client_id}" in METRIC_REQUEST_TOPIC_TEMPLATE
        assert "request/metric" in METRIC_REQUEST_TOPIC_TEMPLATE

    def test_config_request_topic_template_format(self):
        """Test that the config request topic template has correct placeholders."""
        assert "{structure_prefix}" in CONFIG_REQUEST_TOPIC_TEMPLATE
        assert "{client_id}" in CONFIG_REQUEST_TOPIC_TEMPLATE
        assert "request/config" in CONFIG_REQUEST_TOPIC_TEMPLATE

    def test_config_response_topic_template_format(self):
        """Test that the config response topic template has correct placeholders."""
        assert "{structure_prefix}" in CONFIG_RESPONSE_TOPIC_TEMPLATE
        assert "{client_id}" in CONFIG_RESPONSE_TOPIC_TEMPLATE
        assert "{param}" in CONFIG_RESPONSE_TOPIC_TEMPLATE
        assert "{instance}" in CONFIG_RESPONSE_TOPIC_TEMPLATE

    def test_active_discovery_timeout_is_shorter_than_legacy(self):
        """Test that active discovery timeout is shorter than legacy timeout."""
        assert ACTIVE_DISCOVERY_TIMEOUT < LEGACY_DISCOVERY_TIMEOUT
        assert ACTIVE_DISCOVERY_TIMEOUT == 10  # As per implementation plan
        assert LEGACY_DISCOVERY_TIMEOUT == 60  # As per implementation plan

    def test_metric_request_topic_template_formatting(self):
        """Test formatting the metric request topic with actual values."""
        structure_prefix = "ovms/myuser/myvehicle"
        client_id = "ha_ovms_abc123"

        formatted = METRIC_REQUEST_TOPIC_TEMPLATE.format(
            structure_prefix=structure_prefix,
            client_id=client_id,
        )

        assert formatted == "ovms/myuser/myvehicle/client/ha_ovms_abc123/request/metric"


class TestTopicDiscoveryFunctions:
    """Test the topic discovery helper functions."""

    def test_format_structure_prefix(self):
        """Test formatting the structure prefix."""
        from ovms.config_flow.topic_discovery import format_structure_prefix

        config = {
            "topic_structure": DEFAULT_TOPIC_STRUCTURE,
            "topic_prefix": "ovms",
            "mqtt_username": "testuser",
            "vehicle_id": "testvehicle",
        }

        result = format_structure_prefix(config)
        assert result == "ovms/testuser/testvehicle"

    def test_format_structure_prefix_with_missing_username(self):
        """Test formatting structure prefix when username is missing."""
        from ovms.config_flow.topic_discovery import format_structure_prefix

        config = {
            "topic_structure": "{prefix}/{vehicle_id}",
            "topic_prefix": "ovms",
            "mqtt_username": "",
            "vehicle_id": "testvehicle",
        }

        result = format_structure_prefix(config)
        assert result == "ovms/testvehicle"

    def test_format_metric_request_topic(self):
        """Test formatting the metric request topic."""
        from ovms.config_flow.topic_discovery import format_metric_request_topic

        config = {
            "topic_structure": DEFAULT_TOPIC_STRUCTURE,
            "topic_prefix": "ovms",
            "mqtt_username": "testuser",
            "vehicle_id": "testvehicle",
        }
        client_id = "ha_ovms_test123"

        result = format_metric_request_topic(config, client_id)
        assert result == "ovms/testuser/testvehicle/client/ha_ovms_test123/request/metric"


class TestRequestAllMetrics:
    """Test the request_all_metrics function."""

    def test_request_all_metrics_success(self):
        """Test successful metric request."""
        from ovms.config_flow.topic_discovery import request_all_metrics

        # Create mock MQTT client
        mock_result = MagicMock()
        mock_result.rc = 0  # MQTT_ERR_SUCCESS

        mock_mqttc = MagicMock()
        mock_mqttc.publish.return_value = mock_result

        config = {
            "topic_structure": DEFAULT_TOPIC_STRUCTURE,
            "topic_prefix": "ovms",
            "mqtt_username": "testuser",
            "vehicle_id": "testvehicle",
        }
        client_id = "ha_ovms_test123"

        result = request_all_metrics(mock_mqttc, config, client_id, qos=1)

        assert result is True
        mock_mqttc.publish.assert_called_once()

        # Verify the topic and payload
        call_args = mock_mqttc.publish.call_args
        topic = call_args[0][0]
        payload = call_args[0][1]

        assert "request/metric" in topic
        assert payload == "*"

    def test_request_all_metrics_failure(self):
        """Test failed metric request."""
        from ovms.config_flow.topic_discovery import request_all_metrics

        # Create mock MQTT client that returns error
        mock_result = MagicMock()
        mock_result.rc = 1  # Error code

        mock_mqttc = MagicMock()
        mock_mqttc.publish.return_value = mock_result

        config = {
            "topic_structure": DEFAULT_TOPIC_STRUCTURE,
            "topic_prefix": "ovms",
            "mqtt_username": "testuser",
            "vehicle_id": "testvehicle",
        }
        client_id = "ha_ovms_test123"

        result = request_all_metrics(mock_mqttc, config, client_id, qos=1)

        assert result is False

    def test_request_all_metrics_exception(self):
        """Test metric request with exception."""
        from ovms.config_flow.topic_discovery import request_all_metrics

        # Create mock MQTT client that raises exception
        mock_mqttc = MagicMock()
        mock_mqttc.publish.side_effect = Exception("Connection lost")

        config = {
            "topic_structure": DEFAULT_TOPIC_STRUCTURE,
            "topic_prefix": "ovms",
            "mqtt_username": "testuser",
            "vehicle_id": "testvehicle",
        }
        client_id = "ha_ovms_test123"

        result = request_all_metrics(mock_mqttc, config, client_id, qos=1)

        assert result is False


class TestCommandHandlerRemoval:
    """Test that async_send_discovery_command was removed (replaced by metric request)."""

    def test_discovery_command_removed(self):
        """Test that the deprecated method was removed in favor of metric requests."""
        from ovms.mqtt.command_handler import CommandHandler

        # Verify the method has been removed - it's replaced by on-demand metric requests
        assert not hasattr(CommandHandler, "async_send_discovery_command")

    def test_command_handler_has_send_command(self):
        """Test that the primary send_command method still exists."""
        from ovms.mqtt.command_handler import CommandHandler

        # Verify the main method exists
        assert hasattr(CommandHandler, "async_send_command")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
