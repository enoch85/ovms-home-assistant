"""MQTT Client for OVMS Integration."""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Set

from homeassistant.const import ATTR_RESTORED, STATE_UNAVAILABLE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.event import async_call_later

from ..const import (
    DOMAIN,
    ISSUE_TRACKER_URL,
    LOGGER_NAME,
    METRIC_REFRESH_COMMAND,
    METRIC_REQUEST_TOPIC_TEMPLATE,
    METRIC_UNITS_COMMAND,
    CONF_CONFIG_ENTRY_ID,
    CONF_CLIENT_ID,
    CONF_QOS,
    DEFAULT_COMMAND_TIMEOUT,
    DEFAULT_QOS,
    RECONNECT_METRIC_REQUEST_DELAY,
    GPS_ACCURACY_MIN_METERS,
    GPS_ACCURACY_MAX_METERS,
    STALENESS_UNIQUE_ID_MARKER,
    STARTUP_METRIC_REFRESH_DELAY,
    get_platforms_loaded_signal,
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
from ..metrics import METRIC_DEFINITIONS
from ..metrics.units import parse_metric_units

_LOGGER = logging.getLogger(LOGGER_NAME)


class OVMSMQTTClient:
    """MQTT Client for OVMS Integration."""

    def __init__(self, hass: HomeAssistant, config: Dict[str, Any]):
        """Initialize the MQTT Client."""
        self.hass = hass
        self.config = config
        self.config_entry_id = config.get(CONF_CONFIG_ENTRY_ID)
        self.connected = False
        self.discovered_topics = set()
        self.topic_cache = {}
        self._shutting_down = False
        # Cancel handle for the scheduled startup metric refresh (issue #261)
        self._startup_refresh_cancel: Optional[CALLBACK_TYPE] = None
        # Firmware-reported units (see const.METRIC_UNITS_COMMAND). A sensor
        # topic without a definition, whose unit the module has not told us,
        # waits here (topic -> latest payload) while the module is asked, so an
        # entity is never created with a guessed unit the module could supply.
        self._topics_awaiting_units: Dict[str, str] = {}
        # Topics that have waited for an answer already: a topic never triggers
        # a second query, whatever becomes of its entity.
        self._topics_asked_for_units: Set[str] = set()
        self._metric_units_query_running = False
        self._unit_mismatches_logged: Set[str] = set()
        # OVMS publishes its metrics retained, so the broker delivers them the
        # moment we subscribe - while this client is still being set up and
        # cannot send commands yet. The module is asked once setup is complete.
        self._setup_complete = asyncio.Event()

        # Initialize services
        self.naming_service = EntityNamingService(config)
        self.attribute_manager = AttributeManager(config)
        self.staleness_manager = EntityStalenessManager(hass, config)

        # Initialize components
        self.entity_registry = EntityRegistry()
        self.topic_parser = TopicParser(self.config, self.entity_registry)
        self.update_dispatcher = UpdateDispatcher(
            hass, self.entity_registry, self.attribute_manager, self.config
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
                self.hass,
                get_platforms_loaded_signal(self.config_entry_id),
                self._async_platforms_loaded,
            )
        ]

        # Connection manager handles MQTT connection
        if not await self.connection_manager.async_connect():
            return False

        return True

    async def _async_platforms_loaded(self) -> None:
        """Handle platforms loaded event."""
        _LOGGER.info("All platforms loaded, processing entity discovery")
        self._setup_complete.set()

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

        # Firmware without the on-demand feature ignores that request, so
        # entities for metrics OVMS won't republish until their value changes
        # (e.g. v.c.* while parked) would stay restored-unavailable after a
        # restart. Once the request has had its chance, fall back to the
        # universal refresh command when known entities are still missing.
        # See issue #261.
        self._startup_refresh_cancel = async_call_later(
            self.hass,
            STARTUP_METRIC_REFRESH_DELAY,
            self._async_startup_metric_refresh,
        )

    async def _async_startup_metric_refresh(self, _now: datetime) -> None:
        """Request a full metric publish when known entities are still missing.

        Entities are only created once a message arrives on their topic, and
        OVMS publishes non-retained: after its initial on-connect publish it
        only re-sends metrics whose value changed. So after a Home Assistant
        restart, topics that are static while the vehicle is parked (e.g. the
        v.c.* charge metrics sitting at 0) never republish and their entities
        remain restored "unavailable" placeholders until the module reboots
        (issue #261). Edge firmware is healed by the on-demand metric request
        sent on connect; older firmware silently ignores it. When previously
        discovered entities are still missing after the grace period, ask the
        module to republish everything via METRIC_REFRESH_COMMAND - the same
        universal method the ovms.refresh_metrics service uses - so the
        entities are re-created through normal discovery with live data.

        Runs once per setup. If the module is offline the command simply
        fails: its own next reconnection triggers a full publish anyway.
        """
        self._startup_refresh_cancel = None
        if self._shutting_down:
            return
        if not self.connected:
            _LOGGER.debug(
                "Skipping startup metric refresh: not connected to MQTT broker"
            )
            return

        missing = self._count_missing_registry_entities()
        if not missing:
            _LOGGER.debug("Startup metric refresh not needed: no entities missing")
            return

        _LOGGER.info(
            "%d previously discovered entities are still unavailable after "
            "startup, requesting a full metric publish via '%s'",
            missing,
            METRIC_REFRESH_COMMAND,
        )
        result = await self.async_send_command(
            command=METRIC_REFRESH_COMMAND, timeout=DEFAULT_COMMAND_TIMEOUT
        )
        if not result.get("success"):
            _LOGGER.warning(
                "Startup metric refresh command failed (%s); the entities "
                "will recover when the module next reconnects or publishes. "
                "The ovms.refresh_metrics service can be used to retry",
                result.get("error", "no response"),
            )

    def _count_missing_registry_entities(self) -> int:
        """Count this entry's registered entities that have no live data yet.

        Covers entities Home Assistant knows from a previous run whose topics
        have not produced a message this boot: their states are either the
        registry's restored "unavailable" placeholders or, very early in
        startup, not written at all. Disabled entities and the staleness
        diagnostic sensor (not fed by an MQTT topic) are excluded.

        Returns:
            Number of entities still waiting for their first MQTT message.
        """
        if not self.config_entry_id:
            return 0

        entity_registry = er.async_get(self.hass)
        missing = 0
        for entry in er.async_entries_for_config_entry(
            entity_registry, self.config_entry_id
        ):
            if entry.platform != DOMAIN or entry.disabled_by is not None:
                continue
            if entry.unique_id and STALENESS_UNIQUE_ID_MARKER in entry.unique_id:
                continue

            state = self.hass.states.get(entry.entity_id)
            if state is None or (
                state.state == STATE_UNAVAILABLE and state.attributes.get(ATTR_RESTORED)
            ):
                missing += 1
        return missing

    async def _on_message_received(self, topic: str, payload: str) -> None:
        """Handle message received from MQTT broker."""
        self.message_count += 1

        # Check if this is a command response and route it to the command handler
        # This ensures command responses (client/rr/response/*) are properly
        # routed to complete pending command futures instead of being treated
        # as regular entity data. Done before the per-client filter below so
        # our own responses still reach the handler.
        if "client/rr/response" in topic:
            _LOGGER.debug("Routing command response topic: %s", topic)
            self.command_handler.process_response(topic, payload)
            return

        # Drop the rest of the /client/ subtree before any state is recorded.
        # Other OVMS clients (the OVMS Connect mobile app, a second HA
        # instance, shared-vehicle users) publish presence and per-client
        # state under client/{their_client_id}/... — these are not vehicle
        # metrics and must not pollute topic_cache, discovered_topics, the
        # GPS-quality scan, or entity discovery. Filtering here also keeps
        # the startup metric-request gate in _async_platforms_loaded honest:
        # `if not self.discovered_topics` must only see real vehicle data.
        # See issue #216.
        if self.topic_parser.is_per_client_topic(topic):
            return

        # Store in topic cache
        self.topic_cache[topic] = {
            "payload": payload,
            "timestamp": asyncio.get_event_loop().time(),
        }

        # Add to discovered topics
        self.discovered_topics.add(topic)

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
            if parsed_data and self._awaits_metric_units(topic, parsed_data):
                self._topics_awaiting_units[topic] = payload
                self._request_metric_units()
            elif parsed_data:
                await self._async_create_topic_entities(topic, payload, parsed_data)
        else:
            # Existing topic, update entity
            self.update_dispatcher.dispatch_update(topic, payload)

    async def _async_create_topic_entities(
        self, topic: str, payload: str, parsed_data: Dict[str, Any]
    ) -> None:
        """Create the primary entity of a parsed topic and its related entities."""
        await self.entity_factory.async_create_entities(topic, payload, parsed_data)

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

    def _awaits_metric_units(self, topic: str, parsed_data: Dict[str, Any]) -> bool:
        """Return True if this topic's entity must wait for the module's units.

        Only a sensor without a metric definition depends on them, and only
        while the module has not described that metric; everything else is
        created immediately, exactly as before.
        """
        return (
            topic not in self._topics_asked_for_units
            and parsed_data.get("entity_type") == "sensor"
            and not parsed_data.get("metric_defined", True)
            and parsed_data.get("metric_path") not in self.topic_parser.reported_units
        )

    def _request_metric_units(self) -> None:
        """Ask the module for its metric units, unless it is being asked already."""
        if self._metric_units_query_running:
            return
        # Background task: the command can take its full timeout when the
        # module is offline, and must not hold up Home Assistant's startup.
        # Created on the config entry, as Home Assistant asks of integrations,
        # so it is cancelled when the entry is unloaded.
        entry = self.hass.config_entries.async_get_entry(self.config_entry_id)
        if entry is None:
            # The entry is gone, so this client is being torn down.
            return
        self._metric_units_query_running = True
        entry.async_create_background_task(
            self.hass,
            self._async_load_metric_units(),
            name=f"ovms_metric_units_{self.config_entry_id}",
        )

    async def _async_load_metric_units(self) -> None:
        """Learn metric units from the module, then create the waiting entities.

        MQTT carries bare values, so the unit of a metric without a definition
        could only be guessed from its topic name. METRIC_UNITS_COMMAND makes
        the module list every metric with its native unit - the unit Server V3
        publishes in - which removes the guessing for any vehicle and firmware
        without a definition having to exist. On failure (module offline,
        firmware older than 3.3.004, rate limit) nothing is learned and the
        waiting topics get the topic-name guess, the behaviour before this.

        The module only lists a unit for metrics that have a value, so a metric
        it sets later (charge metrics while parked, for one) is asked for when
        its topic first shows up.
        """
        try:
            await self._setup_complete.wait()
            # async_send_command never raises: every failure comes back as
            # success=False, so the waiting topics below are always released.
            result = await self.async_send_command(
                command=METRIC_UNITS_COMMAND, timeout=DEFAULT_COMMAND_TIMEOUT
            )
            response = result.get("response")
            units: Dict[str, Optional[str]] = {}
            if result.get("success") and isinstance(response, str):
                units = parse_metric_units(response)
            self.topic_parser.reported_units.update(units)
            _LOGGER.info("Module described %d of its metrics", len(units))
            self._log_unit_mismatches(units)
        finally:
            self._metric_units_query_running = False

        waiting, self._topics_awaiting_units = self._topics_awaiting_units, {}
        self._topics_asked_for_units.update(waiting)
        for topic, payload in waiting.items():
            if self._shutting_down:
                return
            parsed_data = self.topic_parser.parse_topic(topic, payload)
            if not parsed_data:
                continue
            try:
                await self._async_create_topic_entities(topic, payload, parsed_data)
            except Exception as ex:  # pylint: disable=broad-except
                _LOGGER.error(
                    "Failed to create entity for topic %s: %s", topic, ex, exc_info=True
                )

    def _log_unit_mismatches(self, units: Dict[str, Optional[str]]) -> None:
        """Warn when a metric definition disagrees with the module's unit.

        The definition still wins (it also works offline and on old firmware),
        but a disagreement means the displayed number is wrong and the
        definition needs fixing - this surfaces it instead of leaving it
        unnoticed.
        """
        mismatches = {
            name: f"{name} (module: {unit}, defined: {METRIC_DEFINITIONS[name]['unit']})"
            for name, unit in sorted(units.items())
            if unit is not None
            and name not in self._unit_mismatches_logged
            and name in METRIC_DEFINITIONS
            and METRIC_DEFINITIONS[name].get("unit")
            and str(METRIC_DEFINITIONS[name]["unit"]) != unit
        }
        if mismatches:
            self._unit_mismatches_logged.update(mismatches)
            _LOGGER.warning(
                "The OVMS module reports other units than this integration "
                "defines for: %s. Please report this at %s",
                ", ".join(mismatches.values()),
                ISSUE_TRACKER_URL,
            )

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
        was_connected = self.connected
        self.connected = connected

        if not connected:
            self.reconnect_count += 1
        elif connected and not was_connected:
            # Just connected/reconnected - request all metrics to quickly refresh state
            # This uses the on-demand feature in OVMS edge firmware
            # Older firmware will ignore this, but retained messages + passive
            # publishes will still work
            is_reconnect = self.reconnect_count > 0
            if is_reconnect:
                _LOGGER.info("Reconnected to MQTT broker, requesting metrics refresh")
            else:
                _LOGGER.info("Connected to MQTT broker, requesting initial metrics")
            # Use run_coroutine_threadsafe since this callback runs in paho thread
            asyncio.run_coroutine_threadsafe(
                self._async_request_metrics_on_reconnect(),
                self.hass.loop,
            )

    async def _async_request_metrics_on_reconnect(self) -> None:
        """Request all metrics after reconnecting to quickly refresh entity states.

        This is called automatically after a successful reconnection.
        Uses a small delay to ensure subscriptions are fully established first.
        """
        try:
            # Small delay to ensure subscriptions are active
            await asyncio.sleep(RECONNECT_METRIC_REQUEST_DELAY)

            if self.connected:
                await self.async_request_metrics("*")
        except asyncio.CancelledError:
            # Task was cancelled (e.g., during shutdown) - expected, don't log
            pass
        except (OSError, ValueError) as ex:
            # Non-critical - passive updates will still work
            _LOGGER.debug("Metric request on reconnect failed (non-critical): %s", ex)

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
            qos = self.config.get(CONF_QOS, DEFAULT_QOS)
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

        # Cancel a still-pending startup metric refresh
        if self._startup_refresh_cancel is not None:
            self._startup_refresh_cancel()
            self._startup_refresh_cancel = None

        # Clean up listeners
        for listener_remove in getattr(self, "_cleanup_listeners", []):
            listener_remove()

        # Cancel the command handler's background cleanup task
        if hasattr(self, "command_handler"):
            await self.command_handler.async_shutdown()

        # Shutdown staleness manager
        if hasattr(self, "staleness_manager"):
            await self.staleness_manager.async_shutdown()

        # Cancel any pending GPS coalescing timer
        if hasattr(self, "update_dispatcher"):
            self.update_dispatcher.async_shutdown()

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
