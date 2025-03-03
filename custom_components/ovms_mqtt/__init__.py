"""Open Vehicle Monitoring System (OVMS) MQTT Integration for Home Assistant."""
import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# This integration is config entry only
CONFIG_SCHEMA = cv.config_entry_only_config_schema(cv.schema_with_slug_keys)

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the OVMS MQTT integration."""
    _LOGGER.debug("Setting up OVMS MQTT integration")
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up OVMS MQTT from a config entry."""
    _LOGGER.debug("Setting up OVMS MQTT config entry")

    # Initialize MQTT component if not already done
    if not hass.config_entries.async_entries("mqtt"):
        _LOGGER.warning("MQTT integration is not set up. OVMS MQTT integration requires MQTT")
        return False

    # Forward the setup to the sensor platform using the newer method
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    # Register update listener
    entry.async_on_unload(
        entry.add_update_listener(async_update_options)
    )

    return True

async def async_update_options(hass: HomeAssistant, entry: ConfigEntry):
    """Update options."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    _LOGGER.debug("Unloading OVMS MQTT config entry")

    # Unsubscribe from MQTT topics
    if DOMAIN in hass.data and 'subscription' in hass.data[DOMAIN]:
        _LOGGER.debug("Unsubscribing from MQTT topics")
        hass.data[DOMAIN]['subscription']()
    
    # Unload the platform
    result = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    
    # Clean up data
    if DOMAIN in hass.data:
        hass.data.pop(DOMAIN)

    return result
