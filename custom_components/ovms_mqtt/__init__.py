import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
import voluptuous as vol

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Define an empty configuration schema
CONFIG_SCHEMA = vol.Schema({})

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the OVMS MQTT integration."""
    _LOGGER.debug("Setting up OVMS MQTT integration")
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up OVMS MQTT from a config entry."""
    _LOGGER.debug("Setting up OVMS MQTT config entry")

    # Forward the setup to the sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    _LOGGER.debug("Unloading OVMS MQTT config entry")

    # Forward the unload to the sensor platform
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")

    return True
