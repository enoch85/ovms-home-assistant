"""MQTT connection manager for OVMS integration."""
import asyncio
import logging
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
        
        # Fallback: generate client_id if missing (should not happen after migration)
        if not client_id:
            import hashlib
            import uuid
            host = self.config.get(CONF_HOST, "unknown")
            vehicle_id = self.config.get(CONF_VEHICLE_ID, "unknown")
            fallback_base = f"{host}_{vehicle_id}_{uuid.uuid4().hex[:4]}"
            client_id = f"ha_ovms_{hashlib.md5(fallback_base.encode()).hexdigest()[:12]}"
            _LOGGER.warning("Client ID was missing, generated fallback: %s", client_id)
        
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

            # Allow self-signed certificates if verification is disabled
            if not verify_ssl:
                _LOGGER.debug("SSL certificate verification disabled")
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE

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
                _LOGGER.info("Disconnected from MQTT broker: %s", rc)

                # Schedule reconnection if not intentional disconnect
                if rc != 0:
                    _LOGGER.warning(
                        "Unintentional disconnect. Scheduling reconnection attempt."
                    )
                    asyncio.run_coroutine_threadsafe(
                        self._async_reconnect(),
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
            if hasattr(mqtt, "ReasonCodes"):
                try:
                    reason_code = mqtt.ReasonCodes(mqtt.CMD_CONNACK, rc)
                    _LOGGER.info(
                        "Connected to MQTT broker with result: %s", reason_code
                    )
                except (TypeError, AttributeError):
                    _LOGGER.info(
                        "Connected to MQTT broker with result code: %s", rc
                    )
            else:
                _LOGGER.info(
                    "Connected to MQTT broker with result code: %s", rc
                )

            if rc == 0:
                self.connected = True

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

                _LOGGER.error("Failed to connect to MQTT broker: %s", rc)
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

    async def _async_reconnect(self) -> None:
        """Reconnect to the MQTT broker with exponential backoff."""
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

        # Calculate backoff time based on reconnect count
        backoff = min(
            30, 2 ** min(self.reconnect_count, 5)
        )  # Cap at 30 seconds
        reconnect_msg = f"Reconnecting in {backoff} seconds (attempt #{self.reconnect_count})"
        _LOGGER.info(reconnect_msg)

        try:
            await asyncio.sleep(backoff)

            # Check again if we're shutting down after the sleep
            if self._shutting_down or self.connected:
                return

            # Use clean_session=False for persistent sessions
            if hasattr(mqtt, "MQTTv5"):
                try:
                    client_options = {"clean_start": False}
                    await self.hass.async_add_executor_job(
                        self.client.reconnect, **client_options
                    )
                except TypeError:
                    # Fallback for older clients without clean_start parameter
                    await self.hass.async_add_executor_job(
                        self.client.reconnect
                    )
            else:
                await self.hass.async_add_executor_job(self.client.reconnect)
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.exception("Failed to reconnect to MQTT broker: %s", ex)
            # Schedule another reconnect attempt
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
