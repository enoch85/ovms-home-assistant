"""Open Vehicle Monitoring System (OVMS) MQTT Integration for Home Assistant."""
import logging
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX
from .mqtt_handler import async_cleanup_entities

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the OVMS MQTT integration."""
    _LOGGER.debug("Setting up OVMS MQTT integration")

    # Initialize the domain data
    hass.data.setdefault(DOMAIN, {})
    
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OVMS MQTT from a config entry."""
    _LOGGER.info("Setting up OVMS MQTT integration from config entry")
    
    # Store the entry ID in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(entry.entry_id, {})
    
    # Log configuration
    topic_prefix = entry.data.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
    _LOGGER.info(f"Using MQTT topic prefix: {topic_prefix}")
    
    # Forward the setup to the sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register update listener for config entry changes
    entry.async_on_unload(entry.add_update_listener(config_entry_update_listener))
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading OVMS MQTT integration config entry")
    
    # Unsubscribe from MQTT topics if handler exists
    if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        data_handler = hass.data[DOMAIN][entry.entry_id].get("data_handler")
        if data_handler and hasattr(data_handler, "async_unsubscribe"):
            await data_handler.async_unsubscribe()
    
    # Unload the sensor platform
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    # Clean up entities from registry
    if unload_ok:
        await async_cleanup_entities(hass, entry)
    
    # Remove config entry from hass.data
    if unload_ok and DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    
    return unload_ok


async def config_entry_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle config entry update."""
    _LOGGER.debug("Config entry updated, reloading OVMS MQTT integration")
    await hass.config_entries.async_reload(entry.entry_id)
