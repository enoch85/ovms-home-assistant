"""The OVMS MQTT integration."""
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import config_validation as cv

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ovms_mqtt"

# Define a config schema (empty since this integration is configured via MQTT)
CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the OVMS MQTT integration."""
    _LOGGER.info("OVMS MQTT integration setup")
    return True
