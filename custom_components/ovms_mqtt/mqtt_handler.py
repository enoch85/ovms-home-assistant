"""MQTT message handling for OVMS integration."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.components import mqtt
from homeassistant.helpers.entity_registry import (
    async_get as async_get_entity_registry,
    EntityRegistry,
)

from .const import (
    DOMAIN,
    CONF_TOPIC_PREFIX,
    DEFAULT_TOPIC_PREFIX,
    CONF_VEHICLE_ID,
    DEFAULT_VEHICLE_ID,
    CONF_QOS,
    DEFAULT_QOS,
)
from .entity_handler import process_ovms_message

_LOGGER = logging.getLogger(__name__)


async def async_setup_mqtt_handler(hass: HomeAssistant, entry: ConfigEntry) -> List[callable]:
    """Set up MQTT subscription and message handling."""
    # Extract configuration
    topic_prefix = entry.data.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
    vehicle_id = entry.data.get(CONF_VEHICLE_ID, DEFAULT_VEHICLE_ID)
    qos = entry.data.get(CONF_QOS, DEFAULT_QOS)
    
    # Initialize entity storage if not exists
    if entry.entry_id not in hass.data[DOMAIN]:
        hass.data[DOMAIN][entry.entry_id] = {
            "entities": {},
            "config": dict(entry.data),
            "unsub": [],
        }
    
    @callback
    async def message_received(msg):
        """Handle new MQTT messages."""
        topic = msg.topic
        payload = msg.payload
        
        # Debug log incoming messages
        _LOGGER.debug("Received message on topic %s", topic)
        
        # Process the OVMS message to extract entity data
        entity_data = process_ovms_message(topic, payload)
        if not entity_data:
            return
        
        # Generate a unique entity ID for Home Assistant
        # Use the unique_id from entity_data to ensure consistency
        unique_id = entity_data["unique_id"]
        
        # Check if we already have this entity
        entities = hass.data[DOMAIN][entry.entry_id]["entities"]
        
        # Store or update entity
        if unique_id not in entities:
            # Store new entity
            _LOGGER.debug("Creating new entity with unique_id: %s from topic %s", unique_id, topic)
            entities[unique_id] = entity_data
            
            # Signal platform to create entity
            async_dispatcher_send(hass, f"{DOMAIN}_{entry.entry_id}_new_entity", unique_id)
        else:
            # Update existing entity state
            entities[unique_id].update({
                "state": entity_data["state"],
                "last_updated": entity_data["last_updated"],
            })
            
            # Signal state update
            async_dispatcher_send(hass, f"{DOMAIN}_{entry.entry_id}_state_update", unique_id)

    # Subscribe to all topics for this vehicle
    subscribe_topic = f"{topic_prefix}/{vehicle_id}/#"
    _LOGGER.debug("Subscribing to MQTT topic: %s", subscribe_topic)
    unsub = await mqtt.async_subscribe(
        hass, subscribe_topic, message_received, qos
    )
    
    return [unsub]


async def async_cleanup_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Clean up entities when unloading the integration."""
    try:
        entity_registry = await async_get_entity_registry(hass)
        
        # Get entity entries for this config entry
        entries = async_entries_for_config_entry(
            entity_registry, entry.entry_id
        )
        
        # Remove each entity
        for entity_id in entries:
            entity_registry.async_remove(entity_id)
    except Exception as e:
        _LOGGER.error("Error cleaning up entities: %s", e)


def async_entries_for_config_entry(
    registry: EntityRegistry, config_entry_id: str
) -> List[str]:
    """Return entries for a specific config entry."""
    return [
        entity_id
        for entity_id, entry in registry.entities.items()
        if entry.config_entry_id == config_entry_id
    ]
