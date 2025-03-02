"""Open Vehicle Monitoring System (OVMS) MQTT Integration for Home Assistant."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .sensor import async_setup_entry

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the OVMS MQTT component."""
    # This function is called when the integration is loaded.
    # It doesn't need to do anything for this integration.
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up OVMS MQTT from a config entry."""
    _LOGGER.debug("Setting up OVMS MQTT config entry")

    # Forward the setup to the sensor platform
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "sensor")
    )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    _LOGGER.debug("Unloading OVMS MQTT config entry")

    # Forward the unload to the sensor platform
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")

    return True
