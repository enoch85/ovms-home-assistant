"""MQTT connection manager for OVMS integration."""
import asyncio
import logging
import random
import time
from typing import Any, Dict, Optional, Callable

import paho.mqtt.client as mqtt

from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant, callback

from ..const import (
    CONF_CLIENT_ID,
    CONF_MQTT_USERNAME,
    CONF_QOS,
    CONF_TOPIC_PREFIX,
    CONF_TOPIC_STRUCTURE,
    CONF_VEHICLE_ID,
    CONF_VERIFY_SSL,
    DEFAULT_TOPIC_STRUCTURE,
    DEFAULT_VERIFY_SSL,
    LOGGER_NAME,
    TOPIC_TEMPLATE,
)

_LOGGER = logging.getLogger(LOGGER_NAME)

# Maximum number of reconnection attempts before giving up
MAX_RECONNECTION_ATTEMPTS = 10

# Universal MQTT reason codes (OASIS MQTT v3.1.1 and v5.0 standards)
# These codes are universal across all MQTT brokers
MQTT_REASON_CODES = {
    # MQTT v3.1.1 CONNACK return codes (Section 3.2.2.3)
    0: "Connection accepted",
    1: "Connection refused - unacceptable protocol version", 
    2: "Connection refused - identifier rejected",
    3: "Connection refused - server unavailable",
    4: "Connection refused - bad username or password",
    5: "Connection refused - not authorized",
    # MQTT v5.0 additional reason codes (backwards compatible)
    128: "Unspecified error",
    129: "Malformed packet",
    130: "Protocol error", 
    131: "Implementation specific error",
    132: "Unsupported protocol version",
    133: "Client identifier not valid",
    134: "Bad username or password",
    135: "Not authorized",
    136: "Server unavailable",
    137: "Server busy",
    138: "Banned",
    139: "Server shutting down",
    140: "Bad authentication method",
    141: "Keep alive timeout",
    142: "Session taken over",
    143: "Topic filter invalid",
    144: "Topic name invalid",
}

class MQTTConnectionManager:
    """Manages MQTT connection for OVMS integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: Dict[str, Any],
        message_callback: Callable[[str, str], None],
        connection_callback: Callable[[bool], None],
    ):
        """Initialize the MQTT connection manager."""
        self.hass = hass
        self.config = config
        self.client = None
        self.connected = False
        self._shutting_down = False
        self.reconnect_count = 0
        self.message_callback = message_callback
        self.connection_callback = connection_callback

        # Format the structure prefix
        self.structure_prefix = self._format_structure_prefix()

        # Status tracking
        self._status_topic = None
        self._connected_payload = "online"

    def _format_structure_prefix(self) -> str:
        """Format the topic structure prefix based on configuration."""
        try:
            structure = self.config.get(
                CONF_TOPIC_STRUCTURE, DEFAULT_TOPIC_STRUCTURE
            )
            prefix = self.config.get(CONF_TOPIC_PREFIX)
            vehicle_id = self.config.get(CONF_VEHICLE_ID)
            mqtt_username = self.config.get(CONF_MQTT_USERNAME, "")

            # Replace the variables in the structure
            structure_prefix = structure.format(
                prefix=prefix,
                vehicle_id=vehicle_id,
                mqtt_username=mqtt_username,
            )

            _LOGGER.debug("Formatted structure prefix: %s", structure_prefix)
            return structure_prefix
        except Exception as ex:
            _LOGGER.exception("Error formatting structure prefix: %s", ex)
            # Fallback to a simple default
            return f"{prefix}/{vehicle_id}"

    async def async_setup(self) -> bool:
        """Set up the MQTT client."""
        _LOGGER.debug("Setting up MQTT connection manager")

        # Initialize empty tracking sets/dictionaries
        self._shutting_down = False

        # Create the MQTT client
        self.client = await self._create_mqtt_client()
        if not self.client:
            _LOGGER.error("Failed to create MQTT client")
            return False

        # Set up the callbacks
        self._setup_callbacks()

        return True

    async def _create_mqtt_client(self) -> mqtt.Client:
        """Create and configure the MQTT client."""
        client_id = self.config.get(CONF_CLIENT_ID)
        _LOGGER.debug("MQTT Connection: client_id from config: %s", client_id)
        
        # Fallback: generate stable client_id if missing (should not happen after migration)
        if not client_id:
            import hashlib
            host = self.config.get(CONF_HOST, "unknown")
            username = self.config.get(CONF_USERNAME, "unknown")
            vehicle_id = self.config.get(CONF_VEHICLE_ID, "unknown")
            _LOGGER.debug("MQTT Connection: Fallback values - host=%s, username=%s, vehicle_id=%s", host, username, vehicle_id)
            # Include username to prevent collisions when multiple users have same vehicle_id
            # Hash input combines unique identifiers while keeping username private in logs
            client_id_base = f"{host}_{username}_{vehicle_id}"
            client_id = f"ha_ovms_{hashlib.sha256(client_id_base.encode()).hexdigest()[:12]}"
            _LOGGER.warning("Client ID was missing, generated stable fallback: %s", client_id)
        
        protocol = mqtt.MQTTv5 if hasattr(mqtt, "MQTTv5") else mqtt.MQTTv311

        _LOGGER.debug("Creating MQTT client with ID: %s", client_id)
        try:
            client = mqtt.Client(client_id=client_id, protocol=protocol)
        except Exception as ex:
            _LOGGER.error("Failed to create MQTT client: %s", ex)
            return None

        # Configure authentication if provided
        username = self.config.get(CONF_USERNAME)
        if username and client:
            password = self.config.get(CONF_PASSWORD)
            _LOGGER.debug("Setting username and password for MQTT client")
            client.username_pw_set(
                username=username,
                password=password,
            )

        # Configure TLS if needed
        if self.config.get(CONF_PORT) == 8883:
            _LOGGER.debug("Enabling SSL/TLS for port 8883")
            # pylint: disable=import-outside-toplevel
            import ssl

            verify_ssl = self.config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)

            # Use executor to avoid blocking the event loop
            context = await self.hass.async_add_executor_job(
                ssl.create_default_context
            )

            if not verify_ssl:
                # When verification is disabled, use compatible settings
                _LOGGER.debug("SSL certificate verification disabled")
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            else:
                # When verification is enabled, use secure defaults
                _LOGGER.debug("SSL certificate verification enabled, using secure TLS settings")
                context.minimum_version = ssl.TLSVersion.TLSv1_2

            client.tls_set_context(context)

        # Add Last Will and Testament message
        self._status_topic = f"{self.structure_prefix}/status"
        will_payload = "offline"
        will_qos = self.config.get(CONF_QOS, 1)
        will_retain = True

        client.will_set(
            self._status_topic, will_payload, will_qos, will_retain
        )

        # Add MQTT v5 properties when available
        if (
            hasattr(mqtt, "MQTTv5")
            and hasattr(mqtt, "Properties")
            and hasattr(mqtt, "PacketTypes")
        ):
            try:
                properties = mqtt.Properties(mqtt.PacketTypes.CONNECT)
                properties.UserProperty = (
                    "client_type",
                    "home_assistant_ovms",
                )
                properties.UserProperty = ("version", "1.0.0")
                client.connect_properties = properties
            except (TypeError, AttributeError) as ex:
                _LOGGER.debug("Failed to set MQTT v5 properties: %s", ex)
                # Continue without properties

        return client

    def _get_reason_message(self, reason_code: int) -> str:
        """Get human-readable message for MQTT reason code."""
        return MQTT_REASON_CODES.get(reason_code, f"Unknown reason code: {reason_code}")

    def _should_retry_connection(self, reason_code: int) -> bool:
        """Determine if connection should be retried based on reason code."""
        # Don't retry for these permanent failures
        permanent_failures = {
            1,   # Unacceptable protocol version
            2,   # Identifier rejected  
            4,   # Bad username or password
            5,   # Not authorized
            129, # Malformed packet
            130, # Protocol error
            132, # Unsupported protocol version
            133, # Client identifier not valid
            134, # Bad username or password (v5)
            135, # Not authorized (v5)
            143, # Topic filter invalid
            144, # Topic name invalid
        }
        return reason_code not in permanent_failures

    def _get_retry_delay(self, attempt: int) -> float:
        """Calculate retry delay with exponential backoff and jitter."""
        # Base delay with exponential backoff (cap at 60 seconds)
        base_delay = min(60, 2 ** min(attempt, 6))
        # Add jitter (±25% random variation) to prevent thundering herd
        jitter = base_delay * 0.25 * (2 * random.random() - 1)
        return max(1.0, base_delay + jitter)

    def _setup_callbacks(self) -> None:
        """Set up the MQTT callbacks."""
        # pylint: disable=unused-argument

        # Handle different MQTT protocol versions
        if hasattr(mqtt, "MQTTv5"):

            def on_connect(client, userdata, flags, rc, properties=None):
                """Handle connection result."""
                self._on_connect_callback(client, userdata, flags, rc)

        else:

            def on_connect(client, userdata, flags, rc):
                """Handle connection result for MQTT v3."""
                self._on_connect_callback(client, userdata, flags, rc)

        def on_disconnect(client, userdata, rc, properties=None):
            """Handle disconnection."""
            self.connected = False

            # Notify the client
            if self.connection_callback:
                self.connection_callback(False)

            # Only increment reconnect count and log if not shutting down
            if not self._shutting_down:
                self.reconnect_count += 1
                
                # Enhanced disconnect logging
                if rc == 0:
                    _LOGGER.info("Cleanly disconnected from MQTT broker")
                else:
                    reason_message = self._get_reason_message(rc)
                    _LOGGER.warning("Disconnected from MQTT broker (code %d): %s", rc, reason_message)

                # Schedule reconnection if not intentional disconnect
                if rc != 0:
                    _LOGGER.info("Scheduling reconnection attempt with enhanced backoff")
                    asyncio.run_coroutine_threadsafe(
                        self._async_reconnect(rc),
                        self.hass.loop,
                    )
            else:
                _LOGGER.debug(
                    "Disconnected during shutdown, not attempting reconnect"
                )

        def on_message(client, userdata, msg):
            """Handle incoming messages."""
            try:
                # Try to decode payload
                try:
                    payload = msg.payload.decode("utf-8")
                except UnicodeDecodeError:
                    payload = "<binary data>"

                # Process the message
                if self.message_callback:
                    asyncio.run_coroutine_threadsafe(
                        self.message_callback(msg.topic, payload),
                        self.hass.loop,
                    )
            except Exception as ex:
                _LOGGER.exception("Error in message handler: %s", ex)

        # Set the callbacks
        self.client.on_connect = on_connect
        self.client.on_disconnect = on_disconnect
        self.client.on_message = on_message

    def _on_connect_callback(self, client, userdata, flags, rc):
        """Common connection callback for different MQTT versions."""
        try:
            # Get human-readable reason message
            reason_message = self._get_reason_message(rc)
            
            if rc == 0:
                self.connected = True
                _LOGGER.info("Connected to MQTT broker: %s", reason_message)

                # Notify the client
                if self.connection_callback:
                    self.connection_callback(True)

                # Reset reconnect count on successful connection
                self.reconnect_count = 0

                # Re-subscribe if we get disconnected
                asyncio.run_coroutine_threadsafe(
                    self.async_subscribe_topics(),
                    self.hass.loop,
                )

                # Publish online status when connected
                if self._status_topic:
                    client.publish(
                        self._status_topic,
                        self._connected_payload,
                        qos=self.config.get(CONF_QOS, 1),
                        retain=True,
                    )
            else:
                self.connected = False

                # Notify the client
                if self.connection_callback:
                    self.connection_callback(False)

                # Enhanced error logging with reason code details
                _LOGGER.error("Failed to connect to MQTT broker (code %d): %s", rc, reason_message)
                
                # Log additional guidance for common errors
                if rc in [4, 134]:  # Bad username or password
                    _LOGGER.error("Check your MQTT username and password in the configuration")
                elif rc in [5, 135]:  # Not authorized
                    _LOGGER.error("MQTT user is not authorized - check broker ACL settings")
                elif rc in [3, 136]:  # Server unavailable
                    _LOGGER.error("MQTT broker is unavailable - check if broker is running and accessible")
                elif rc == 137:  # Server busy
                    _LOGGER.warning("MQTT broker is busy - will retry with backoff")
        except Exception as ex:
            _LOGGER.exception("Error in connect callback: %s", ex)

    async def async_connect(self) -> bool:
        """Connect to the MQTT broker."""
        host = self.config.get(CONF_HOST)
        port = self.config.get(CONF_PORT)

        _LOGGER.debug("Connecting to MQTT broker at %s:%s", host, port)

        try:
            # Connect using the executor to avoid blocking
            await self.hass.async_add_executor_job(
                self.client.connect,
                host,
                port,
                60,  # Keep alive timeout
            )

            # Start the loop in a separate thread
            self.client.loop_start()

            # Wait for the connection to establish
            for _ in range(10):  # Try for up to 5 seconds
                if self.connected:
                    _LOGGER.info("Successfully connected to MQTT broker")
                    return True
                await asyncio.sleep(0.5)

            _LOGGER.error("Timed out waiting for MQTT connection")
            return False

        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.exception("Failed to connect to MQTT broker: %s", ex)
            return False

    async def _async_reconnect(self, reason_code: Optional[int] = None) -> None:
        """Reconnect to the MQTT broker with enhanced exponential backoff."""
        # Check if we're shutting down or reached the maximum number of attempts
        if self._shutting_down:
            _LOGGER.debug("Not reconnecting because shutdown is in progress")
            return

        if self.reconnect_count > MAX_RECONNECTION_ATTEMPTS:
            _LOGGER.error(
                "Maximum reconnection attempts (%d) reached, giving up",
                MAX_RECONNECTION_ATTEMPTS,
            )
            return

        # Check if we should retry based on the reason code
        if reason_code is not None and not self._should_retry_connection(reason_code):
            reason_message = self._get_reason_message(reason_code)
            _LOGGER.error(
                "Not retrying connection due to permanent failure (code %d): %s", 
                reason_code, reason_message
            )
            return

        # Calculate backoff time with jitter
        backoff = self._get_retry_delay(self.reconnect_count)
        reconnect_msg = f"Reconnecting in {backoff:.1f} seconds (attempt #{self.reconnect_count})"
        
        if reason_code is not None:
            reason_message = self._get_reason_message(reason_code)
            reconnect_msg += f" - Previous failure: {reason_message}"
        
        _LOGGER.info(reconnect_msg)

        try:
            await asyncio.sleep(backoff)

            # Check again if we're shutting down after the sleep
            if self._shutting_down or self.connected:
                return

            # Use clean_session=False for persistent sessions
            if hasattr(mqtt, "MQTTv5"):
                try:
                    # For MQTT v5, set clean_start parameter directly on client
                    original_clean_start = getattr(self.client, 'clean_start', None)
                    self.client.clean_start = False
                    await self.hass.async_add_executor_job(self.client.reconnect)
                    # Restore original setting if it existed
                    if original_clean_start is not None:
                        self.client.clean_start = original_clean_start
                except (TypeError, AttributeError):
                    # Fallback for older clients without clean_start parameter
                    await self.hass.async_add_executor_job(self.client.reconnect)
            else:
                await self.hass.async_add_executor_job(self.client.reconnect)
        except Exception as ex:  # pylint: disable=broad-except
            if "SSL" in str(ex) or "TLS" in str(ex):
                _LOGGER.error(
                    "SSL/TLS error during MQTT reconnection: %s. "
                    "This may be due to broker issues or network connectivity problems. "
                    "Try rebooting your OVMS module if issue persists.",
                    ex
                )
            else:
                _LOGGER.exception("Failed to reconnect to MQTT broker: %s", ex)
            
            # Schedule another reconnect attempt (no reason code available from exception)
            if not self._shutting_down:
                asyncio.create_task(self._async_reconnect())

    async def async_subscribe_topics(self) -> None:
        """Subscribe to the OVMS topics."""
        if not self.connected:
            _LOGGER.warning("Cannot subscribe to topics, not connected")
            return

        try:
            # Format the topic
            qos = self.config.get(CONF_QOS)

            # Subscribe to all topics under the structure prefix
            topic = TOPIC_TEMPLATE.format(
                structure_prefix=self.structure_prefix
            )

            _LOGGER.info("Subscribing to OVMS topic: %s", topic)
            await self.hass.async_add_executor_job(
                self.client.subscribe, topic, qos
            )

            # Add a subscription with vehicle ID but without username
            # Handle the case where topics might use different username patterns
            vehicle_id = self.config.get(CONF_VEHICLE_ID, "")
            prefix = self.config.get(CONF_TOPIC_PREFIX, "")
            if vehicle_id and prefix:
                alternative_topic = f"{prefix}/+/{vehicle_id}/#"
                _LOGGER.info(
                    "Also subscribing to alternative topic pattern: %s",
                    alternative_topic,
                )
                await self.hass.async_add_executor_job(
                    self.client.subscribe, alternative_topic, qos
                )
        except Exception as ex:
            _LOGGER.exception("Error subscribing to topics: %s", ex)

    async def async_publish(self, topic: str, payload: str, qos: Optional[int] = None, retain: bool = False) -> bool:
        """Publish a message to the MQTT broker."""
        if not self.connected:
            _LOGGER.warning("Cannot publish message, not connected")
            return False

        try:
            if qos is None:
                qos = self.config.get(CONF_QOS, 1)

            await self.hass.async_add_executor_job(
                self.client.publish, topic, payload, qos, retain
            )
            return True
        except Exception as ex:
            _LOGGER.exception("Error publishing message: %s", ex)
            return False

    async def async_shutdown(self) -> None:
        """Shutdown the MQTT client."""
        _LOGGER.info("Shutting down MQTT connection")

        # Set the shutdown flag to prevent reconnection attempts
        self._shutting_down = True

        if self.client:
            _LOGGER.debug("Stopping MQTT client loop")
            try:
                # Try to publish offline status before disconnecting
                if self._status_topic and self.connected:
                    _LOGGER.debug("Publishing offline status")
                    await self.hass.async_add_executor_job(
                        self.client.publish,
                        self._status_topic,
                        "offline",
                        self.config.get(CONF_QOS, 1),
                        True  # Retain
                    )

                # Stop the loop and disconnect
                await self.hass.async_add_executor_job(self.client.loop_stop)
                await self.hass.async_add_executor_job(self.client.disconnect)
                _LOGGER.debug("MQTT client disconnected")
            except Exception as ex:
                _LOGGER.exception("Error stopping MQTT client: %s", ex)
