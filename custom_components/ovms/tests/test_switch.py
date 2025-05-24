"""Unit tests for the OVMS Switch platform."""

import pytest
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo

# Import the class to be tested
from custom_components.ovms.sensor.switch import OVMSSwitch

# Import metrics for testing definitions
from custom_components.ovms.metrics.vehicles.nissan_leaf import NISSAN_LEAF_METRICS

# Mock homeassistant.helpers.entity.async_generate_entity_id
# as it's called during OVMSSwitch initialization if hass is provided
@patch('homeassistant.helpers.entity.async_generate_entity_id', return_value="switch.test_switch")
def test_nissan_leaf_metric_definitions(mock_generate_entity_id):
    """Test that Nissan Leaf switch metric definitions are as expected."""
    climate_metric = NISSAN_LEAF_METRICS.get("xnl.v.c.climate_control")
    assert climate_metric is not None
    assert climate_metric["entity_type"] == "switch"
    assert climate_metric["command"] == "climatecontrol"
    assert climate_metric["state_on"] == "Climate Control \non\n"
    assert climate_metric["state_off"] == "Climate Control \noff\n"
    assert "payload_on" not in climate_metric  # Should use default "on"
    assert "payload_off" not in climate_metric # Should use default "off"

    charge_metric = NISSAN_LEAF_METRICS.get("xnl.v.c.charge_control")
    assert charge_metric is not None
    assert charge_metric["entity_type"] == "switch"
    assert charge_metric["command"] == "charge"
    assert charge_metric["payload_on"] == "start"
    assert charge_metric["payload_off"] == "stop"
    assert charge_metric["state_on"] == "Charge has been started\n"
    assert charge_metric["state_off"] == "Charge has been stopped\n"

@pytest.fixture
def mock_hass():
    """Fixture for a mocked HomeAssistant object."""
    return AsyncMock(spec=HomeAssistant)

@pytest.fixture
def mock_command_function():
    """Fixture for a mocked command function."""
    return AsyncMock(return_value={"success": True})

@pytest.fixture
def minimal_device_info():
    """Fixture for a minimal DeviceInfo object."""
    return DeviceInfo(
        identifiers={("ovms", "test_device_id")},
        name="Test OVMS Device",
        manufacturer="OVMS",
        model="TestModel",
    )

@patch('homeassistant.helpers.entity.async_generate_entity_id', return_value="switch.test_climate_switch")
async def test_ovms_switch_climate_control(
    mock_generate_entity_id, mock_hass, mock_command_function, minimal_device_info
):
    """Test OVMSSwitch for Nissan Leaf Climate Control."""
    metric_info = NISSAN_LEAF_METRICS["xnl.v.c.climate_control"]
    switch_attributes = {
        "command": metric_info["command"],
        "state_on": metric_info["state_on"],
        "state_off": metric_info["state_off"],
        # Include other attributes that might be passed from the metric definition
        "icon": metric_info.get("icon"),
        "category": metric_info.get("category"),
        "state_topic_suffix": metric_info.get("state_topic_suffix"),
    }

    switch = OVMSSwitch(
        unique_id="test_climate_switch",
        name="Test Climate Switch",
        topic="ovms/test/metric/xnl.v.c.climate_control",
        initial_state=metric_info["state_off"], # Start in off state
        device_info=minimal_device_info,
        attributes=switch_attributes,
        command_function=mock_command_function,
        hass=mock_hass,
    )

    # Test turning on
    await switch.async_turn_on()
    mock_command_function.assert_called_with(command="climatecontrol", parameters="on")
    assert switch.is_on is True

    # Test turning off
    await switch.async_turn_off()
    mock_command_function.assert_called_with(command="climatecontrol", parameters="off")
    assert switch.is_on is False

    # Test state parsing
    assert switch._parse_state(metric_info["state_on"]) is True
    assert switch._parse_state("Climate Control \non\n") is True # Direct check
    assert switch._parse_state(metric_info["state_off"]) is False
    assert switch._parse_state("Climate Control \noff\n") is False # Direct check
    # Test case/space variation (assuming strip().lower() in implementation)
    assert switch._parse_state("CLIMATE CONTROL \nON\n") is True
    assert switch._parse_state(" climate control \noff\n ") is False

@patch('homeassistant.helpers.entity.async_generate_entity_id', return_value="switch.test_charge_switch")
async def test_ovms_switch_charge_control(
    mock_generate_entity_id, mock_hass, mock_command_function, minimal_device_info
):
    """Test OVMSSwitch for Nissan Leaf Charge Control."""
    metric_info = NISSAN_LEAF_METRICS["xnl.v.c.charge_control"]
    switch_attributes = {
        "command": metric_info["command"],
        "payload_on": metric_info["payload_on"],
        "payload_off": metric_info["payload_off"],
        "state_on": metric_info["state_on"],
        "state_off": metric_info["state_off"],
        "icon": metric_info.get("icon"),
        "category": metric_info.get("category"),
        "state_topic_suffix": metric_info.get("state_topic_suffix"),
    }

    switch = OVMSSwitch(
        unique_id="test_charge_switch",
        name="Test Charge Switch",
        topic="ovms/test/metric/xnl.v.c.charge_control",
        initial_state=metric_info["state_off"], # Start in off state
        device_info=minimal_device_info,
        attributes=switch_attributes,
        command_function=mock_command_function,
        hass=mock_hass,
    )

    # Test turning on
    await switch.async_turn_on()
    mock_command_function.assert_called_with(command="charge", parameters="start")
    assert switch.is_on is True

    # Test turning off
    await switch.async_turn_off()
    mock_command_function.assert_called_with(command="charge", parameters="stop")
    assert switch.is_on is False

    # Test state parsing
    assert switch._parse_state(metric_info["state_on"]) is True
    assert switch._parse_state("Charge has been started\n") is True # Direct check
    assert switch._parse_state(metric_info["state_off"]) is False
    assert switch._parse_state("Charge has been stopped\n") is False # Direct check
    assert switch._parse_state("CHARGE HAS BEEN STARTED\n") is True # Case variation

@patch('homeassistant.helpers.entity.async_generate_entity_id', return_value="switch.test_generic_switch")
async def test_ovms_switch_fallback_parsing(
    mock_generate_entity_id, mock_hass, mock_command_function, minimal_device_info
):
    """Test OVMSSwitch fallback state parsing when no custom states are defined."""
    switch_attributes = {
        "command": "generic_command",
        # No state_on, state_off, payload_on, payload_off
    }

    switch = OVMSSwitch(
        unique_id="test_generic_switch",
        name="Test Generic Switch",
        topic="ovms/test/metric/generic.switch",
        initial_state="off", # Start in off state
        device_info=minimal_device_info,
        attributes=switch_attributes,
        command_function=mock_command_function,
        hass=mock_hass,
    )

    # Test turning on (should use default "on" payload)
    await switch.async_turn_on()
    mock_command_function.assert_called_with(command="generic_command", parameters="on")
    assert switch.is_on is True

    # Test turning off (should use default "off" payload)
    await switch.async_turn_off()
    mock_command_function.assert_called_with(command="generic_command", parameters="off")
    assert switch.is_on is False

    # Test fallback state parsing
    assert switch._parse_state("on") is True
    assert switch._parse_state("ON") is True
    assert switch._parse_state("Off") is False
    assert switch._parse_state("OFF") is False
    assert switch._parse_state("1") is True
    assert switch._parse_state("0") is False
    assert switch._parse_state("true") is True
    assert switch._parse_state("True") is True
    assert switch._parse_state("false") is False
    assert switch._parse_state("False") is False
    assert switch._parse_state("yes") is True
    assert switch._parse_state("no") is False
    assert switch._parse_state("enabled") is True
    assert switch._parse_state("disabled") is False
    assert switch._parse_state("active") is True
    assert switch._parse_state("inactive") is False

    # JSON parsing
    assert switch._parse_state('{"value": "on"}') is True
    assert switch._parse_state('{"value": "off"}') is False
    assert switch._parse_state('{"state": true}') is True
    assert switch._parse_state('{"status": 1}') is True
    assert switch._parse_state('{"status": 0}') is False # Assuming 0 is off

    # Invalid states
    assert switch._parse_state("invalid_state_value") is False
    assert switch._parse_state("random") is False
    assert switch._parse_state("") is False # Empty string
    assert switch._parse_state('{"value": "other"}') is False # JSON but not on/off

@patch('homeassistant.helpers.entity.async_generate_entity_id', return_value="switch.test_init_state_switch")
async def test_ovms_switch_initial_state(
    mock_generate_entity_id, mock_hass, mock_command_function, minimal_device_info
):
    """Test OVMSSwitch initial state setting."""
    metric_info_climate = NISSAN_LEAF_METRICS["xnl.v.c.climate_control"]
    
    # Test initial state "on"
    switch_on = OVMSSwitch(
        unique_id="test_init_on", name="Test Init On", topic="topic1",
        initial_state=metric_info_climate["state_on"],
        device_info=minimal_device_info,
        attributes={
            "command": "cmd1", 
            "state_on": metric_info_climate["state_on"], 
            "state_off": metric_info_climate["state_off"]
        },
        command_function=mock_command_function, hass=mock_hass
    )
    assert switch_on.is_on is True

    # Test initial state "off"
    switch_off = OVMSSwitch(
        unique_id="test_init_off", name="Test Init Off", topic="topic2",
        initial_state=metric_info_climate["state_off"],
        device_info=minimal_device_info,
        attributes={
            "command": "cmd2",
            "state_on": metric_info_climate["state_on"],
            "state_off": metric_info_climate["state_off"]
        },
        command_function=mock_command_function, hass=mock_hass
    )
    assert switch_off.is_on is False

    # Test initial state with fallback parsing
    switch_fallback_on = OVMSSwitch(
        unique_id="test_init_fallback_on", name="Test Fallback On", topic="topic3",
        initial_state="1", # Fallback "on"
        device_info=minimal_device_info,
        attributes={"command": "cmd3"},
        command_function=mock_command_function, hass=mock_hass
    )
    assert switch_fallback_on.is_on is True

    switch_fallback_off = OVMSSwitch(
        unique_id="test_init_fallback_off", name="Test Fallback Off", topic="topic4",
        initial_state="Disabled", # Fallback "off"
        device_info=minimal_device_info,
        attributes={"command": "cmd4"},
        command_function=mock_command_function, hass=mock_hass
    )
    assert switch_fallback_off.is_on is False

    switch_fallback_json = OVMSSwitch(
        unique_id="test_init_fallback_json", name="Test Fallback Json", topic="topic5",
        initial_state='{"value": true}', # Fallback "on" via JSON
        device_info=minimal_device_info,
        attributes={"command": "cmd5"},
        command_function=mock_command_function, hass=mock_hass
    )
    assert switch_fallback_json.is_on is True

# Minimal DeviceInfo as it's required by the constructor
DEVICE_INFO_MINIMAL = DeviceInfo(
    identifiers={("ovms", "test_device")},
    name="Test Device",
)

# Mock for async_generate_entity_id
MOCK_ASYNC_GENERATE_ENTITY_ID = patch(
    'homeassistant.helpers.entity.async_generate_entity_id',
    return_value="switch.generated_id"
)

# Further tests could include:
# - Behavior when command_function returns {"success": False}
# - _determine_switch_type (though it's complex and might be better with integration tests)
# - async_added_to_hass and state restoration (requires more mocking of HA internals)
# - _process_json_payload for attribute extraction (partially covered by fallback parsing)

# To run these tests:
# 1. Ensure pytest and pytest-asyncio are installed: pip install pytest pytest-asyncio
# 2. Navigate to the root of your Home Assistant configuration or custom_components directory.
# 3. Run pytest: pytest path/to/custom_components/ovms/tests/test_switch.py
#    (Adjust path as necessary)
#
# Example: If your HA config is in /config, and this file is in 
# /config/custom_components/ovms/tests/test_switch.py, then from /config:
# pytest custom_components/ovms/tests/test_switch.py
#
# Or, if you are in the custom_components/ovms directory:
# pytest tests/test_switch.py

# Note: This test suite assumes that the `SIGNAL_ADD_ENTITIES` and `SIGNAL_UPDATE_ENTITY`
# are not strictly necessary for the direct testing of the OVMSSwitch methods here.
# If their absence caused issues (e.g., due to logic in async_added_to_hass that
# relies on them for setup), they would need to be mocked using patch.object or similar.
# For instance, if `async_dispatcher_connect` needed to be a no-op:
# @patch('homeassistant.helpers.dispatcher.async_dispatcher_connect', return_value=lambda: None)
# would be added to relevant test functions or fixtures.
# However, for this specific class and the methods tested, it seems direct calls are okay.

if __name__ == "__main__":
    # This allows running the tests directly with `python test_switch.py`
    # (though pytest is the recommended way).
    # You'll need to install pytest and run `pytest` in the terminal.
    # For direct execution, you might need to adjust imports or paths
    # depending on your environment setup.
    print("Running tests with pytest is recommended.")
    print("Example: pytest custom_components/ovms/tests/test_switch.py")
    # Example of how to run a specific test function if pytest is not used (simplified)
    # import asyncio
    # async def run_one():
    #     mock_gen_id = MOCK_ASYNC_GENERATE_ENTITY_ID.start()
    #     await test_ovms_switch_climate_control(None, mock_hass(), mock_command_function(), minimal_device_info())
    #     MOCK_ASYNC_GENERATE_ENTITY_ID.stop()
    # asyncio.run(run_one())
