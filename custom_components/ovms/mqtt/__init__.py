"""MQTT Client for OVMS Integration."""
import asyncio
import logging
from typing import Dict, Any, Optional

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from ..const import (
    DOMAIN,
    LOGGER_NAME,
    SIGNAL_PLATFORMS_LOADED,
)

from .connection import MQTTConnectionManager
from .topic_parser import TopicParser
from .entity_factory import EntityFactory
from .entity_registry import EntityRegistry
from .update_dispatcher import UpdateDispatcher
from .command_handler import CommandHandler

_LOGGER = logging.getLogger(LOGGER_NAME)

class OVMSMQTTClient:
    """MQTT Client for OVMS Integration."""

    def __init__(self, hass: HomeAssistant, config: Dict[str, Any]):
        """Initialize the MQTT Client."""
        self.hass = hass
        self.config = config
        self.connected = False
        self.discovered_topics = set()
        self.topic_cache = {}
        self._shutting_down = False

        # Initialize components
        self.entity_registry = EntityRegistry()
        self.topic_parser = TopicParser(self.config, self.entity_registry)
        self.update_dispatcher = UpdateDispatcher(hass, self.entity_registry)
        self.entity_factory = EntityFactory(
            hass,
            self.entity_registry,
            self.update_dispatcher,
            self.config
        )
        self.command_handler = CommandHandler(hass, config)

        # Initialize connection manager last as it depends on other components
        self.connection_manager = MQTTConnectionManager(
            hass,
            config,
            self._on_message_received,
            self._on_connection_change
        )

        # For tracking metrics and diagnostics
        self.message_count = 0
        self.reconnect_count = 0
        self.entity_types = {}  # For diagnostics

    async def async_setup(self) -> bool:
        """Set up the MQTT client."""
        _LOGGER.debug("Setting up MQTT client")

        # Initialize components
        if not await self.connection_manager.async_setup():
            return False

        # Subscribe to platforms loaded event
        self.hass.helpers.dispatcher.async_dispatcher_connect(
            SIGNAL_PLATFORMS_LOADED, self._async_platforms_loaded
        )

        # Connection manager handles MQTT connection
        if not await self.connection_manager.async_connect():
            return False

        return True

    async def _async_platforms_loaded(self) -> None:
        """Handle platforms loaded event."""
        _LOGGER.info("All platforms loaded, processing entity discovery")

        # Process queued entities from entity factory
        await self.entity_factory.async_process_queued_entities()

        # Try to discover by subscribing again (in case initial subscription failed)
        await self.connection_manager.async_subscribe_topics()

        # Try to discover by sending a test command if no topics found
        if not self.discovered_topics and self.connected:
            _LOGGER.info("No topics discovered yet, trying to discover by sending a test command")
            await self.command_handler.async_send_discovery_command()

    async def _on_message_received(self, topic: str, payload: str) -> None:
        """Handle message received from MQTT broker."""
        self.message_count += 1

        # Store in topic cache
        self.topic_cache[topic] = {
            "payload": payload,
            "timestamp": asyncio.get_event_loop().time(),
        }

        # Add to discovered topics
        self.discovered_topics.add(topic)

        # Process message and create/update entities
        if topic not in self.entity_registry.topics:
            # New topic, create entity
            parsed_data = self.topic_parser.parse_topic(topic, payload)
            if parsed_data:
                await self.entity_factory.async_create_entities(topic, payload, parsed_data)
        else:
            # Existing topic, update entity
            self.update_dispatcher.dispatch_update(topic, payload)

    def _on_connection_change(self, connected: bool) -> None:
        """Handle connection state changes."""
        self.connected = connected
        if not connected:
            self.reconnect_count += 1

    @property
    def structure_prefix(self) -> str:
        """Get the structure prefix."""
        return self.connection_manager.structure_prefix

    async def async_send_command(self, **kwargs) -> Dict[str, Any]:
        """Send a command to the OVMS module."""
        return await self.command_handler.async_send_command(**kwargs)

    async def async_shutdown(self) -> None:
        """Shutdown the MQTT client."""
        self._shutting_down = True
        await self.connection_manager.async_shutdown()
