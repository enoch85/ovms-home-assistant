"""Tests for the OVMS sensor platform."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricPotential,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity import DeviceInfo

from custom_components.ovms.sensor import OVMSSensor, NUMERIC_DEVICE_CLASSES


class TestOVMSSensor:
    """Test the OVMSSensor class."""

    @pytest.fixture
    def mock_hass(self):
        """Fixture to create a mock hass object."""
        hass = MagicMock(spec=HomeAssistant)
        hass.states = {}
        return hass

    @pytest.fixture
    def basic_sensor_data(self):
        """Fixture with basic sensor test data."""
        return {
            "unique_id": "ovms_test_vehicle_battery_voltage",
            "name": "battery_voltage",
            "topic": "ovms/test_user/test_vehicle/v/b/voltage",
            "initial_state": "400.5",
            "device_info": DeviceInfo(
                identifiers={("ovms", "test_vehicle")},
                name="OVMS - Test Vehicle",
                manufacturer="Open Vehicles",
                model="OVMS Module",
            ),
            "attributes": {
                "category": "battery",
                "topic": "ovms/test_user/test_vehicle/v/b/voltage",
            },
            "friendly_name": "Battery Voltage",
        }

    @pytest.fixture
    def mock_restore_state(self):
        """Mock restore state method."""
        with patch("custom_components.ovms.sensor.RestoreEntity.async_get_last_state") as mock_restore:
            yield mock_restore

    def test_init(self, basic_sensor_data):
        """Test sensor initialization."""
        with patch("custom_components.ovms.sensor.get_metric_by_path") as mock_get_path:
            # Configure the mock to return battery voltage metric info
            mock_get_path.return_value = {
                "name": "Battery Voltage",
                "device_class": SensorDeviceClass.VOLTAGE,
                "state_class": SensorStateClass.MEASUREMENT,
                "unit": UnitOfElectricPotential.VOLT,
                "category": "battery",
                "icon": "mdi:flash",
            }
            
            # Initialize sensor
            sensor = OVMSSensor(**basic_sensor_data)
            
            # Check basic properties
            assert sensor.unique_id == basic_sensor_data["unique_id"]
            assert sensor.name == basic_sensor_data["friendly_name"]
            assert sensor._topic == basic_sensor_data["topic"]
            assert sensor.device_info == basic_sensor_data["device_info"]
            
            # Check the determined device class, etc.
            assert sensor.device_class == SensorDeviceClass.VOLTAGE
            assert sensor.state_class == SensorStateClass.MEASUREMENT
            assert sensor.native_unit_of_measurement == UnitOfElectricPotential.VOLT
            assert sensor.icon == "mdi:flash"
            
            # Check that the value was parsed correctly
            assert sensor.native_value == 400.5

    def test_parse_value_numeric(self, basic_sensor_data):
        """Test parsing numeric values."""
        with patch("custom_components.ovms.sensor.get_metric_by_path") as mock_get_path:
            mock_get_path.return_value = {
                "device_class": SensorDeviceClass.VOLTAGE,
                "state_class": SensorStateClass.MEASUREMENT,
            }
            
            sensor = OVMSSensor(**basic_sensor_data)
            
            # Test various numeric formats
            assert sensor._parse_value("123") == 123
            assert sensor._parse_value("123.45") == 123.45
            assert sensor._parse_value("-10.5") == -10.5
            
            # Test special values that should return None for numeric sensors
            assert sensor._parse_value("unknown") is None
            assert sensor._parse_value("unavailable") is None
            assert sensor._parse_value("none") is None
            assert sensor._parse_value("") is None
            assert sensor._parse_value(None) is None

    def test_parse_value_json(self, basic_sensor_data):
        """Test parsing JSON values."""
        with patch("custom_components.ovms.sensor.get_metric_by_path") as mock_get_path:
            mock_get_path.return_value = {
                "device_class": SensorDeviceClass.TEMPERATURE,
                "state_class": SensorStateClass.MEASUREMENT,
            }
            
            sensor = OVMSSensor(**basic_sensor_data)
            
            # Test JSON object with value field
            assert sensor._parse_value('{"value": 22.5, "unit": "C"}') == 22.5
            
            # Test JSON object with state field
            assert sensor._parse_value('{"state": 23.5, "timestamp": 1234567890}') == 23.5
            
            # Test simple JSON values
            assert sensor._parse_value('42') == 42
            assert sensor._parse_value('true') == 1  # Boolean converted to int for numeric sensor
            
            # Test that attributes are extracted
            sensor._parse_value('{"value": 24.5, "unit": "C", "timestamp": 1234567890}')
            assert "unit" in sensor.extra_state_attributes
            assert sensor.extra_state_attributes["unit"] == "C"
            assert "device_timestamp" in sensor.extra_state_attributes
            assert sensor.extra_state_attributes["device_timestamp"] == 1234567890

    def test_parse_cell_array(self, basic_sensor_data):
        """Test parsing comma-separated cell values."""
        with patch("custom_components.ovms.sensor.get_metric_by_path") as mock_get_path:
            mock_get_path.return_value = {
                "device_class": SensorDeviceClass.VOLTAGE,
                "state_class": SensorStateClass.MEASUREMENT,
                "has_cell_data": True,
            }
            
            # Add platform for _register_cell_sensors
            basic_sensor_data["platform"] = MagicMock()
            basic_sensor_data["platform"].async_add_entities = AsyncMock()
            
            sensor = OVMSSensor(**basic_sensor_data)
            sensor.hass = MagicMock()
            
            # Test comma-separated cell values
            result = sensor._parse_value("3.7, 3.8, 3.75, 3.82")
            
            # Verify that the average is returned
            assert result == pytest.approx(3.7675)
            
            # Verify that cell values are stored in attributes
            assert "cell_values" in sensor.extra_state_attributes
            assert len(sensor.extra_state_attributes["cell_values"]) == 4
            assert sensor.extra_state_attributes["cell_count"] == 4
            
            # Verify cell sensors are queued for creation
            assert sensor._cell_sensors_created is True
            assert len(sensor._cell_registry) == 4

    async def test_restore_state(self, mock_hass, basic_sensor_data, mock_restore_state):
        """Test restoring state from persistence."""
        with patch("custom_components.ovms.sensor.get_metric_by_path") as mock_get_path:
            mock_get_path.return_value = {
                "device_class": SensorDeviceClass.TEMPERATURE,
                "state_class": SensorStateClass.MEASUREMENT,
                "unit": UnitOfTemperature.CELSIUS,
            }
            
            # Create a fake restored state
            restored_state = State(
                entity_id="sensor.test",
                state="22.5",
                attributes={
                    "unit_of_measurement": UnitOfTemperature.CELSIUS,
                    "device_class": SensorDeviceClass.TEMPERATURE,
                    "last_updated": "2023-01-01T00:00:00+00:00",
                    "custom_attr": "test_value",
                }
            )
            mock_restore_state.return_value = restored_state
            
            # Create sensor
            sensor = OVMSSensor(**basic_sensor_data)
            sensor.hass = mock_hass
            
            # Call the added_to_hass method
            await sensor.async_added_to_hass()
            
            # Check that state was restored
            assert sensor.native_value == "22.5"
            
            # Check that custom attributes were restored
            assert "custom_attr" in sensor.extra_state_attributes
            assert sensor.extra_state_attributes["custom_attr"] == "test_value"

    def test_requires_numeric_value(self, basic_sensor_data):
        """Test the requires_numeric_value method."""
        sensor = OVMSSensor(**basic_sensor_data)
        
        # Test with numeric device classes
        for device_class in NUMERIC_DEVICE_CLASSES:
            sensor._attr_device_class = device_class
            sensor._attr_state_class = None
            assert sensor._requires_numeric_value() is True
            
        # Test with measurement state class
        sensor._attr_device_class = None
        sensor._attr_state_class = SensorStateClass.MEASUREMENT
        assert sensor._requires_numeric_value() is True
        
        # Test with total state class
        sensor._attr_state_class = SensorStateClass.TOTAL
        assert sensor._requires_numeric_value() is True
        
        # Test with total increasing state class
        sensor._attr_state_class = SensorStateClass.TOTAL_INCREASING
        assert sensor._requires_numeric_value() is True
        
        # Test with non-numeric classes
        sensor._attr_device_class = SensorDeviceClass.DATE
        sensor._attr_state_class = None
        assert sensor._requires_numeric_value() is False
