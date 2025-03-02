"""The OVMS MQTT integration."""
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ovms_mqtt"

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the OVMS MQTT integration."""
    _LOGGER.info("OVMS MQTT integration setup")
    return True
