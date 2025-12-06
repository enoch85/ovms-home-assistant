"""Tests for GPS accuracy calculation improvements (Phase 3).

This module tests the GPS accuracy handling using standardized constants
and the preference for v.p.gpssq over HDOP when available.
"""

import pytest
from unittest.mock import MagicMock, patch
import sys
from pathlib import Path

# Add the custom_components to the path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components"))

from ovms.const import (
    GPS_ACCURACY_MIN_METERS,
    GPS_ACCURACY_MAX_METERS,
    GPS_HDOP_METERS_MULTIPLIER,
)


class TestGPSAccuracyConstants:
    """Test the GPS accuracy constants."""

    def test_min_accuracy_is_positive(self):
        """Test that minimum accuracy is a positive value."""
        assert GPS_ACCURACY_MIN_METERS > 0
        assert GPS_ACCURACY_MIN_METERS == 5

    def test_max_accuracy_is_greater_than_min(self):
        """Test that maximum accuracy is greater than minimum."""
        assert GPS_ACCURACY_MAX_METERS > GPS_ACCURACY_MIN_METERS
        assert GPS_ACCURACY_MAX_METERS == 100

    def test_hdop_multiplier_is_positive(self):
        """Test that HDOP multiplier is positive."""
        assert GPS_HDOP_METERS_MULTIPLIER > 0
        assert GPS_HDOP_METERS_MULTIPLIER == 5


class TestGPSSQMetricDefinition:
    """Test the v.p.gpssq metric definition."""

    def test_gpssq_metric_exists(self):
        """Test that v.p.gpssq metric is defined."""
        from ovms.metrics.common.location import LOCATION_METRICS

        assert "v.p.gpssq" in LOCATION_METRICS

    def test_gpssq_metric_uses_percentage(self):
        """Test that v.p.gpssq uses percentage unit (not dBm)."""
        from ovms.metrics.common.location import LOCATION_METRICS
        from homeassistant.const import PERCENTAGE

        metric = LOCATION_METRICS["v.p.gpssq"]
        assert metric["unit"] == PERCENTAGE

    def test_gpssq_metric_has_correct_description(self):
        """Test that v.p.gpssq has description with quality thresholds."""
        from ovms.metrics.common.location import LOCATION_METRICS

        metric = LOCATION_METRICS["v.p.gpssq"]
        description = metric["description"]

        # Should mention quality thresholds
        assert "0-100" in description or "100" in description
        assert "<30" in description or "30" in description

    def test_gpssq_metric_no_signal_strength_device_class(self):
        """Test that v.p.gpssq doesn't use SIGNAL_STRENGTH device class."""
        from ovms.metrics.common.location import LOCATION_METRICS
        from homeassistant.components.sensor import SensorDeviceClass

        metric = LOCATION_METRICS["v.p.gpssq"]

        # Should NOT have SIGNAL_STRENGTH device class (it's percentage, not dBm)
        assert metric.get("device_class") != SensorDeviceClass.SIGNAL_STRENGTH


class TestAttributeManagerGPSAccuracy:
    """Test the AttributeManager GPS accuracy calculations."""

    def test_get_gps_attributes_with_hdop(self):
        """Test GPS accuracy calculation from HDOP."""
        from ovms.attribute_manager import AttributeManager

        manager = AttributeManager({})
        attrs = manager.get_gps_attributes("ovms/user/vehicle/v/p/gpshdop", "2.5")

        assert "gps_hdop" in attrs
        assert attrs["gps_hdop"] == 2.5
        assert "gps_accuracy" in attrs
        # 2.5 * 5 = 12.5 meters
        assert attrs["gps_accuracy"] == 12.5
        assert attrs["gps_accuracy_unit"] == "m"

    def test_get_gps_attributes_with_gpssq(self):
        """Test GPS accuracy calculation from signal quality."""
        from ovms.attribute_manager import AttributeManager

        manager = AttributeManager({})
        attrs = manager.get_gps_attributes("ovms/user/vehicle/v/p/gpssq", "80")

        assert "gps_signal_quality" in attrs
        assert attrs["gps_signal_quality"] == 80
        assert "gps_accuracy" in attrs
        # 100 - 80 = 20 meters
        assert attrs["gps_accuracy"] == 20
        assert attrs["gps_accuracy_unit"] == "m"

    def test_get_gps_attributes_with_low_signal_quality(self):
        """Test GPS accuracy with low signal quality."""
        from ovms.attribute_manager import AttributeManager

        manager = AttributeManager({})
        attrs = manager.get_gps_attributes("ovms/user/vehicle/v/p/gpssq", "10")

        # 100 - 10 = 90 meters
        assert attrs["gps_accuracy"] == 90

    def test_get_gps_attributes_with_excellent_signal_quality(self):
        """Test GPS accuracy with excellent signal quality."""
        from ovms.attribute_manager import AttributeManager

        manager = AttributeManager({})
        attrs = manager.get_gps_attributes("ovms/user/vehicle/v/p/gpssq", "95")

        # 100 - 95 = 5 meters (at minimum)
        assert attrs["gps_accuracy"] == GPS_ACCURACY_MIN_METERS

    def test_get_gps_attributes_respects_minimum_accuracy(self):
        """Test that minimum accuracy floor is respected."""
        from ovms.attribute_manager import AttributeManager

        manager = AttributeManager({})

        # With 100% signal quality, accuracy should be clamped to minimum
        attrs = manager.get_gps_attributes("ovms/user/vehicle/v/p/gpssq", "100")
        assert attrs["gps_accuracy"] == GPS_ACCURACY_MIN_METERS

        # With very low HDOP, accuracy should also be clamped
        attrs = manager.get_gps_attributes("ovms/user/vehicle/v/p/gpshdop", "0.5")
        assert attrs["gps_accuracy"] == GPS_ACCURACY_MIN_METERS

    def test_get_gps_attributes_with_invalid_payload(self):
        """Test handling of invalid GPS payload."""
        from ovms.attribute_manager import AttributeManager

        manager = AttributeManager({})
        attrs = manager.get_gps_attributes("ovms/user/vehicle/v/p/gpssq", "invalid")

        # Should not crash, may have empty or partial attributes
        assert isinstance(attrs, dict)

    def test_get_gps_attributes_with_gps_speed(self):
        """Test GPS speed attribute extraction."""
        from ovms.attribute_manager import AttributeManager

        manager = AttributeManager({})
        attrs = manager.get_gps_attributes("ovms/user/vehicle/v/p/gpsspeed", "65.5")

        assert "gps_speed" in attrs
        assert attrs["gps_speed"] == 65.5


class TestMQTTClientGPSAccuracy:
    """Test the OVMSMQTTClient GPS accuracy method."""

    def test_get_gps_accuracy_prefers_signal_quality(self):
        """Test that get_gps_accuracy prefers gpssq over hdop."""
        from ovms.mqtt import OVMSMQTTClient

        # Create a minimal mock hass
        mock_hass = MagicMock()
        mock_hass.data = {}

        config = {"vehicle_id": "testvehicle"}

        with patch.object(OVMSMQTTClient, "__init__", lambda x, y, z: None):
            client = OVMSMQTTClient.__new__(OVMSMQTTClient)
            client.config = config
            client.gps_quality_topics = {
                "testvehicle": {
                    "signal_quality": {"topic": "v/p/gpssq", "value": 75},
                    "hdop": {"topic": "v/p/gpshdop", "value": 3.0},
                }
            }

            accuracy = client.get_gps_accuracy()

            # Should use signal_quality (100 - 75 = 25), not HDOP (3.0 * 5 = 15)
            assert accuracy == 25

    def test_get_gps_accuracy_falls_back_to_hdop(self):
        """Test that get_gps_accuracy falls back to HDOP when gpssq unavailable."""
        from ovms.mqtt import OVMSMQTTClient

        config = {"vehicle_id": "testvehicle"}

        with patch.object(OVMSMQTTClient, "__init__", lambda x, y, z: None):
            client = OVMSMQTTClient.__new__(OVMSMQTTClient)
            client.config = config
            client.gps_quality_topics = {
                "testvehicle": {
                    "hdop": {"topic": "v/p/gpshdop", "value": 4.0},
                }
            }

            accuracy = client.get_gps_accuracy()

            # Should use HDOP: 4.0 * 5 = 20
            assert accuracy == 20

    def test_get_gps_accuracy_returns_none_when_no_data(self):
        """Test that get_gps_accuracy returns None when no GPS data."""
        from ovms.mqtt import OVMSMQTTClient

        config = {"vehicle_id": "testvehicle"}

        with patch.object(OVMSMQTTClient, "__init__", lambda x, y, z: None):
            client = OVMSMQTTClient.__new__(OVMSMQTTClient)
            client.config = config
            client.gps_quality_topics = {}

            accuracy = client.get_gps_accuracy()

            assert accuracy is None

    def test_get_gps_accuracy_with_specific_vehicle_id(self):
        """Test get_gps_accuracy with specific vehicle ID parameter."""
        from ovms.mqtt import OVMSMQTTClient

        config = {"vehicle_id": "default_vehicle"}

        with patch.object(OVMSMQTTClient, "__init__", lambda x, y, z: None):
            client = OVMSMQTTClient.__new__(OVMSMQTTClient)
            client.config = config
            client.gps_quality_topics = {
                "other_vehicle": {
                    "signal_quality": {"topic": "v/p/gpssq", "value": 60},
                }
            }

            # Should return accuracy for the specified vehicle
            accuracy = client.get_gps_accuracy("other_vehicle")
            assert accuracy == 40  # 100 - 60


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
