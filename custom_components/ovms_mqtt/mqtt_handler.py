"""MQTT message handling for OVMS integration."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

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
    CONF_AVAILABILITY_TIMEOUT,
    DEFAULT_AVAILABILITY_TIMEOUT,
    CONF_TLS_INSECURE,
    DEFAULT_TLS_INSECURE,
    CONF_CERTIFICATE_PATH,
)
from .entity_handler import process_ovms_message

_LOGGER = logging.getLogger(__name__)


async def async_setup_mqtt_handler(
    hass: HomeAssistant, entry: ConfigEntry
) -> List[callable]:
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
    def message_received(msg):
        """Handle new MQTT messages.
        
        Note: This must be a synchronous function as it's a callback.
        """
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
            _LOGGER.debug(
                "Creating new entity with unique_id: %s from topic %s",
                unique_id, topic
            )
            entities[unique_id] = entity_data
            
            # Signal platform to create entity
            async_dispatcher_send(
                hass, f"{DOMAIN}_{entry.entry_id}_new_entity", unique_id
            )
        else:
            # Update existing entity state
            entities[unique_id].update({
                "state": entity_data["state"],
                "last_updated": entity_data["last_updated"],
                "available": True,  # Mark entity as available
            })
            
            # Signal state update
            async_dispatcher_send(
                hass, f"{DOMAIN}_{entry.entry_id}_state_update", unique_id
            )

    # Setup availability topic if configured
    availability_timeout = entry.data.get(
        CONF_AVAILABILITY_TIMEOUT, DEFAULT_AVAILABILITY_TIMEOUT
    )
    if availability_timeout > 0:
        # Set up availability monitoring for entities
        async def monitor_availability():
            """Monitor entity availability based on last update time."""
            import time
            from datetime import datetime, timedelta
            
            while True:
                current_time = datetime.now()
                timeout_delta = timedelta(seconds=availability_timeout)
                
                if entry.entry_id in hass.data.get(DOMAIN, {}):
                    entities = hass.data[DOMAIN][entry.entry_id].get("entities", {})
                    
                    for unique_id, entity_data in entities.items():
                        if "last_updated" in entity_data:
                            try:
                                last_updated = datetime.fromisoformat(
                                    entity_data["last_updated"]
                                )
                                if current_time - last_updated > timeout_delta:
                                    # Mark entity as unavailable
                                    entity_data["available"] = False
                                    # Signal state update
                                    async_dispatcher_send(
                                        hass,
                                        f"{DOMAIN}_{entry.entry_id}_state_update",
                                        unique_id
                                    )
                            except (ValueError, TypeError) as e:
                                _LOGGER.debug(
                                    "Error parsing timestamp for %s: %s", 
                                    unique_id, e
                                )
                
                # Check every 60 seconds
                await asyncio.sleep(60)
        
        # Start availability monitoring task
        hass.async_create_task(monitor_availability())

    # Configure additional MQTT options
    mqtt_options = {}
    
    # Handle SSL/TLS options if configured
    if entry.data.get(CONF_SSL, False):
        import ssl
        
        # Check if certificate verification should be disabled
        tls_insecure = entry.data.get(CONF_TLS_INSECURE, DEFAULT_TLS_INSECURE)
        
        # Check if a certificate path is provided
        cert_path = entry.data.get(CONF_CERTIFICATE_PATH)
        
        mqtt_options["tls_context"] = ssl.create_default_context(
            cafile=cert_path if cert_path else None
        )
        
        if tls_insecure:
            mqtt_options["tls_context"].check_hostname = False
            mqtt_options["tls_context"].verify_mode = ssl.CERT_NONE

    # Subscribe to all topics for this vehicle
    subscribe_topic = f"{topic_prefix}/{vehicle_id}/#"
    _LOGGER.debug("Subscribing to MQTT topic: %s", subscribe_topic)
    
    try:
        unsub = await mqtt.async_subscribe(
            hass, subscribe_topic, message_received, qos, **mqtt_options
        )
        return [unsub]
    except Exception as e:
        _LOGGER.error("Failed to subscribe to MQTT topic %s: %s", subscribe_topic, e)
        return []


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
