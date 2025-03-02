"""The OVMS MQTT integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OVMS MQTT from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Store the config data
    hass.data[DOMAIN][entry.entry_id] = entry.data

    # Forward the setup to the sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload the sensor platform
    await hass.config_entries.async_forward_entry_unload(entry, "sensor")

    # Remove the config data
    hass.data[DOMAIN].pop(entry.entry_id)
    return True
