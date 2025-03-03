"""MQTT message handling for OVMS integration."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, List, Optional, Callable

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
    CONF_CONNECTION_TYPE,
    CONNECTION_TYPE_SECURE,
    CONNECTION_TYPE_WEBSOCKETS_SECURE,
)
from .entity_handler import process_ovms_message

_LOGGER = logging.getLogger(__name__)


class OVMSMQTTHandler:
    """Handler for OVMS MQTT messages."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the MQTT handler."""
        self.hass = hass
        self.entry = entry
        self.entry_id = entry.entry_id
        self.config = dict(entry.data)
        self.subscriptions: List[Callable] = []
        self.topic_prefix = self.config.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
        self.vehicle_id = self.config.get(CONF_VEHICLE_ID, DEFAULT_VEHICLE_ID)
        self.qos = self.config.get(CONF_QOS, DEFAULT_QOS)
        self.availability_timeout = self.config.get(
            CONF_AVAILABILITY_TIMEOUT, DEFAULT_AVAILABILITY_TIMEOUT
        )
        self.availability_task = None

    async def async_setup(self) -> bool:
        """Set up the MQTT handler."""
        _LOGGER.debug("Setting up OVMS MQTT handler")

        # Initialize storage in hass.data if not exists
        if self.entry_id not in self.hass.data[DOMAIN]:
            self.hass.data[DOMAIN][self.entry_id] = {
                "entities": {},
                "config": self.config,
                "data_handler": self,
            }

        # Set up MQTT subscriptions
        success = await self.async_subscribe_topics()
        
        # Start availability monitoring if configured
        if success and self.availability_timeout > 0:
            self.availability_task = self.hass.async_create_task(
                self.monitor_availability()
            )
            
        return success

    async def async_subscribe_topics(self) -> bool:
        """Subscribe to OVMS MQTT topics."""
        _LOGGER.debug(
            "Subscribing to OVMS MQTT topics: prefix=%s, vehicle_id=%s",
            self.topic_prefix, self.vehicle_id
        )
        
        # Generate wildcard topic for all OVMS messages
        topic_filter = f"{self.topic_prefix}/{self.vehicle_id}/#"
        
        try:
            # Subscribe to MQTT topic
            self.subscriptions.append(
                await mqtt.async_subscribe(
                    self.hass,
                    topic_filter,
                    self._message_received,
                    self.qos,
                )
            )
            _LOGGER.debug("Successfully subscribed to topic: %s", topic_filter)
            return True
        except Exception as e:
            _LOGGER.error("Failed to subscribe to MQTT topic %s: %s", topic_filter, e)
            return False

    @callback
    def _message_received(self, msg) -> None:
        """Handle new MQTT messages."""
        topic = msg.topic
        payload = msg.payload
        
        _LOGGER.debug("Received message on topic %s", topic)
        
        # Process the message
        entity_data = process_ovms_message(topic, payload)
        if not entity_data:
            return
        
        # Get the unique ID from the entity data
        unique_id = entity_data["unique_id"]
        
        # Store or update entity
        entities = self.hass.data[DOMAIN][self.entry_id]["entities"]
        
        if unique_id not in entities:
            # New entity
            _LOGGER.debug(
                "Creating new entity with unique_id: %s from topic %s",
                unique_id, topic
            )
            entities[unique_id] = entity_data
            
            # Notify that a new entity is available
            async_dispatcher_send(
                self.hass, f"{DOMAIN}_{self.entry_id}_new_entity", unique_id
            )
        else:
            # Update existing entity
            entities[unique_id].update({
                "state": entity_data["state"],
                "unit": entity_data.get("unit"),
                "last_updated": entity_data["last_updated"],
                "available": True,
            })
            
            # Notify that an entity needs a state update
            async_dispatcher_send(
                self.hass, f"{DOMAIN}_{self.entry_id}_state_update", unique_id
            )

    async def monitor_availability(self) -> None:
        """Monitor entity availability based on last update time."""
        _LOGGER.debug("Starting entity availability monitoring")
        
        from datetime import datetime, timedelta
        
        while True:
            try:
                current_time = datetime.now()
                timeout_delta = timedelta(seconds=self.availability_timeout)
                
                if self.entry_id in self.hass.data.get(DOMAIN, {}):
                    entities = self.hass.data[DOMAIN][self.entry_id].get("entities", {})
                    
                    for unique_id, entity_data in entities.items():
                        if "last_updated" in entity_data:
                            try:
                                last_updated = datetime.fromisoformat(
                                    entity_data["last_updated"]
                                )
                                if current_time - last_updated > timeout_delta:
                                    # Mark entity as unavailable
                                    if entity_data.get("available", True):
                                        entity_data["available"] = False
                                        # Notify that entity availability changed
                                        async_dispatcher_send(
                                            self.hass,
                                            f"{DOMAIN}_{self.entry_id}_state_update",
                                            unique_id
                                        )
                            except (ValueError, TypeError) as e:
                                _LOGGER.debug(
                                    "Error parsing timestamp for %s: %s", 
                                    unique_id, e
                                )
            except Exception as e:
                _LOGGER.error("Error in availability monitoring: %s", e)
                
            # Check every 60 seconds
            await asyncio.sleep(60)

    async def async_unsubscribe(self) -> None:
        """Unsubscribe from all MQTT topics."""
        _LOGGER.debug("Unsubscribing from MQTT topics")
        
        for unsub in self.subscriptions:
            unsub()
        self.subscriptions = []
        
        # Cancel availability monitoring
        if self.availability_task:
            self.availability_task.cancel()
            try:
                await self.availability_task
            except asyncio.CancelledError:
                pass
            self.availability_task = None


async def async_setup_mqtt_handler(
    hass: HomeAssistant, entry: ConfigEntry
) -> Optional[OVMSMQTTHandler]:
    """Set up MQTT handler for OVMS integration."""
    _LOGGER.debug("Creating OVMS MQTT handler")
    
    handler = OVMSMQTTHandler(hass, entry)
    success = await handler.async_setup()
    
    if success:
        return handler
    
    return None


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
            
        _LOGGER.debug("Cleaned up entities for config entry %s", entry.entry_id)
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
