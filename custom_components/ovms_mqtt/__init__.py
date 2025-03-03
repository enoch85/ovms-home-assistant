"""The OVMS MQTT integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .mqtt_handler import async_setup_mqtt_handler, async_cleanup_entities

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OVMS MQTT from a config entry."""
    _LOGGER.debug("Setting up OVMS MQTT integration")
    
    # Initialize storage for entities
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "entities": {},
        "config": dict(entry.data),
        "unsub": [],
    }
    
    # Set up MQTT subscription
    unsub_list = await async_setup_mqtt_handler(hass, entry)
    
    # Store unsubscribe functions
    hass.data[DOMAIN][entry.entry_id]["unsub"] = unsub_list
    
    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register update listener
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options when the config entry options are updated."""
    _LOGGER.debug("Updating OVMS MQTT configuration")
    
    # Update the stored config with the new options
    if entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN][entry.entry_id]["config"].update(entry.options)
    
    # Reload the integration with the new options
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok and entry.entry_id in hass.data[DOMAIN]:
        # Unsubscribe from MQTT topics
        for unsub in hass.data[DOMAIN][entry.entry_id].get("unsub", []):
            unsub()
        
        # Clean up entities from the registry
        await async_cleanup_entities(hass, entry)
        
        # Remove entry data
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok
