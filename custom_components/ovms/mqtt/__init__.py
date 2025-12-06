"""MQTT Client for OVMS Integration."""

import asyncio
import logging
from typing import Dict, Any, Optional, Set

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)

from ..const import (
    DOMAIN,
    LOGGER_NAME,
    SIGNAL_PLATFORMS_LOADED,
    METRIC_REQUEST_TOPIC_TEMPLATE,
    CONF_CLIENT_ID,
    CONF_QOS,
    ACTIVE_DISCOVERY_TIMEOUT,
    GPS_ACCURACY_MIN_METERS,
    GPS_ACCURACY_MAX_METERS,
)

from .connection import MQTTConnectionManager
from .topic_parser import TopicParser
from .entity_factory import EntityFactory
from .entity_registry import EntityRegistry
from .update_dispatcher import UpdateDispatcher
from .command_handler import CommandHandler
from ..naming_service import EntityNamingService
from ..attribute_manager import AttributeManager
from ..entity_staleness_manager import EntityStalenessManager

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

        # Initialize services
        self.naming_service = EntityNamingService(config)
        self.attribute_manager = AttributeManager(config)
        self.staleness_manager = EntityStalenessManager(hass, config)

        # Initialize components
        self.entity_registry = EntityRegistry()
        self.topic_parser = TopicParser(self.config, self.entity_registry)
        self.update_dispatcher = UpdateDispatcher(
            hass, self.entity_registry, self.attribute_manager
        )
        self.entity_factory = EntityFactory(
            hass,
            self.entity_registry,
            self.update_dispatcher,
            self.config,
            self.naming_service,
            self.attribute_manager,
        )
        self.command_handler = CommandHandler(hass, config)

        # Initialize connection manager last as it depends on other components
        self.connection_manager = MQTTConnectionManager(
            hass, config, self._on_message_received, self._on_connection_change
        )

        # For tracking metrics and diagnostics
        self.message_count = 0
        self.reconnect_count = 0
        self.entity_types = {}  # For diagnostics

        # For GPS topic tracking
        self.gps_quality_topics = {}

    async def async_setup(self) -> bool:
        """Set up the MQTT client."""
        _LOGGER.debug("Setting up MQTT client")

        # Initialize components
        if not await self.connection_manager.async_setup():
            return False

        # Subscribe to platforms loaded event - Fixed dispatcher usage
        self._cleanup_listeners = [
            async_dispatcher_connect(
                self.hass, SIGNAL_PLATFORMS_LOADED, self._async_platforms_loaded
            )
        ]

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

        # Request all metrics using on-demand feature (OVMS edge firmware)
        # This replaces the old async_send_discovery_command() workaround
        if not self.discovered_topics and self.connected:
            _LOGGER.info(
                "No topics discovered yet, requesting metrics via on-demand feature"
            )
            await self.async_request_metrics()

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

        # Check if this is a command response and route it to the command handler
        # This ensures command responses (client/rr/response/*) are properly
        # routed to complete pending command futures instead of being treated
        # as regular entity data
        if "client/rr/response" in topic:
            _LOGGER.debug("Routing command response topic: %s", topic)
            self.command_handler.process_response(topic, payload)
            return

        # Track GPS quality topics for location accuracy
        if any(
            kw in topic.lower()
            for kw in ["gpssq", "gps_sq", "gps/sq", "gpshdop", "gps_hdop"]
        ):
            self._track_gps_quality_topic(topic, payload)

        # Process message and create/update entities
        # Use get_entities_for_topic to support multiple entities per topic
        entities_for_topic = self.entity_registry.get_entities_for_topic(topic)
        if not entities_for_topic:
            # New topic, create entity
            parsed_data = self.topic_parser.parse_topic(topic, payload)
            if parsed_data:
                # Create the primary entity
                await self.entity_factory.async_create_entities(
                    topic, payload, parsed_data
                )

                # Create any related entities (e.g., switches for controllable metrics)
                related_entities = self.topic_parser.get_related_entities(parsed_data)
                for related_entity in related_entities:
                    try:
                        await self.entity_factory.async_create_entities(
                            topic, payload, related_entity
                        )
                    except Exception as ex:
                        _LOGGER.error(
                            "Failed to create related entity for topic %s (%s): %s",
                            topic,
                            related_entity.get("entity_type", "unknown"),
                            ex,
                            exc_info=True,
                        )
        else:
            # Existing topic, update entity
            self.update_dispatcher.dispatch_update(topic, payload)

    def _track_gps_quality_topic(self, topic: str, payload: str) -> None:
        """Track GPS quality topics for location accuracy."""
        try:
            value = float(payload)
            vehicle_id = self.config.get("vehicle_id", "")

            # Store by vehicle ID
            if vehicle_id not in self.gps_quality_topics:
                self.gps_quality_topics[vehicle_id] = {}

            # Determine type of GPS quality metric
            if "gpssq" in topic.lower():
                self.gps_quality_topics[vehicle_id]["signal_quality"] = {
                    "topic": topic,
                    "value": value,
                }
            elif "gpshdop" in topic.lower():
                self.gps_quality_topics[vehicle_id]["hdop"] = {
                    "topic": topic,
                    "value": value,
                }
        except (ValueError, TypeError):
            # Not a numeric value
            pass

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

    async def async_request_metrics(self, pattern: str = "*") -> bool:
        """Request metrics from the OVMS module using on-demand feature.

        This uses the on-demand metric request feature in OVMS edge firmware.
        Publishing a pattern to the metric request topic causes OVMS to immediately
        publish all matching metrics to their normal topics.

        Args:
            pattern: Metric pattern to request. Defaults to "*" for all metrics.
                     Examples: "*" (all), "v.b.*" (battery), "v.p.*" (position)

        Returns:
            True if the request was sent successfully, False otherwise.

        Note:
            This feature requires OVMS edge firmware (post-3.3.005).
            Older firmware will simply not respond to the request.
        """
        if not self.connected or not self.connection_manager.connected:
            _LOGGER.warning("Cannot request metrics: not connected to MQTT broker")
            return False

        try:
            client_id = self.config.get(CONF_CLIENT_ID, "")
            if not client_id:
                _LOGGER.warning("Cannot request metrics: no client_id configured")
                return False

            # Format the metric request topic
            metric_request_topic = METRIC_REQUEST_TOPIC_TEMPLATE.format(
                structure_prefix=self.structure_prefix,
                client_id=client_id,
            )

            _LOGGER.debug(
                "Requesting metrics with pattern '%s' via topic: %s",
                pattern,
                metric_request_topic,
            )

            # Publish the request
            qos = self.config.get(CONF_QOS, 1)
            success = await self.connection_manager.async_publish(
                metric_request_topic, pattern, qos=qos
            )

            if success:
                _LOGGER.info(
                    "Successfully published metric request with pattern '%s'", pattern
                )
            else:
                _LOGGER.warning("Failed to publish metric request")

            return success

        except Exception as ex:
            _LOGGER.warning("Error requesting metrics: %s", ex)
            return False

    async def async_shutdown(self) -> None:
        """Shutdown the MQTT client."""
        self._shutting_down = True

        # Clean up listeners
        for listener_remove in getattr(self, "_cleanup_listeners", []):
            listener_remove()

        # Shutdown staleness manager
        if hasattr(self, "staleness_manager"):
            await self.staleness_manager.async_shutdown()

        await self.connection_manager.async_shutdown()

    def get_gps_accuracy(self, vehicle_id: Optional[str] = None) -> Optional[float]:
        """Get GPS accuracy in meters from stored GPS quality data.

        Calculates positional accuracy based on GPS signal quality metric v.p.gpssq.

        Args:
            vehicle_id: Optional vehicle ID. Uses configured vehicle_id if not provided.

        Returns:
            GPS accuracy in meters, or None if no GPS quality data is available.
            Lower values indicate better accuracy.

        Note:
            v.p.gpssq: 0-100% where <30 is unusable, >50 is good, >80 is excellent
            See OVMS firmware changes.txt for metric details.
        """
        if not vehicle_id:
            vehicle_id = self.config.get("vehicle_id", "")

        if not vehicle_id or vehicle_id not in self.gps_quality_topics:
            return None

        gps_data = self.gps_quality_topics[vehicle_id]

        # Use signal_quality (v.p.gpssq) - standard OVMS metric
        if "signal_quality" in gps_data:
            sq = gps_data["signal_quality"]["value"]
            # Signal quality 0-100% maps inversely to accuracy in meters
            # 100% quality = minimum accuracy (best), 0% = maximum accuracy (worst)
            return max(GPS_ACCURACY_MIN_METERS, GPS_ACCURACY_MAX_METERS - sq)

        return None
