"""Global fixtures for OVMS integration tests."""
import pytest
from unittest.mock import patch

# This fixture is used to prevent HomeAssistant from trying to create .homeassistant directories
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations defined in the test dir."""
    yield

# This fixture is used to mock MQTT
@pytest.fixture
def mock_mqtt():
    """Mock MQTT component."""
    with patch("homeassistant.components.mqtt.async_setup", return_value=True), \
         patch("homeassistant.components.mqtt.async_setup_entry", return_value=True):
        yield
