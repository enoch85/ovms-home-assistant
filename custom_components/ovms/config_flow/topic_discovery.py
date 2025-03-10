"""Topic discovery utilities for OVMS config flow."""
import asyncio
import logging
import re
import socket
import traceback
import uuid

import paho.mqtt.client as mqtt  # pylint: disable=import-error

from homeassistant.const import (  # pylint: disable=import-error
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    CONF_PROTOCOL,
)
from homeassistant.core import HomeAssistant  # pylint: disable=import-error

from ..const import (
    CONF_MQTT_USERNAME,
    CONF_TOPIC_PREFIX,
    CONF_TOPIC_STRUCTURE,
    CONF_VEHICLE_ID,
    CONF_QOS,
    CONF_VERIFY_SSL,
    DEFAULT_TOPIC_PREFIX,
    DEFAULT_TOPIC_STRUCTURE,
    DEFAULT_VERIFY_SSL,
    DISCOVERY_TOPIC,
    TOPIC_TEMPLATE,
    COMMAND_TOPIC_TEMPLATE,
    RESPONSE_TOPIC_TEMPLATE,
    LOGGER_NAME,
    ERROR_CANNOT_CONNECT,
    ERROR_TIMEOUT,
    ERROR_UNKNOWN,
)

_LOGGER = logging.getLogger(LOGGER_NAME)


def format_structure_prefix(config):
    """Format the topic structure prefix based on the configuration."""
    structure = config.get(CONF_TOPIC_STRUCTURE, DEFAULT_TOPIC_STRUCTURE)
    prefix = config.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
    vehicle_id = config.get(CONF_VEHICLE_ID, "")
    mqtt_username = config.get(CONF_MQTT_USERNAME, "")

    _LOGGER.debug(
        "Formatting structure prefix with: structure=%s, prefix=%s, vehicle_id=%s, "
        "mqtt_username=%s",
        structure, prefix, vehicle_id, mqtt_username
    )

    # Replace the variables in the structure
    try:
        structure_prefix = structure.format(
            prefix=prefix,
            vehicle_id=vehicle_id,
            mqtt_username=mqtt_username
        )
    except KeyError as e:
        _LOGGER.error(
            "Error formatting structure prefix: %s - Variables available: prefix=%s, "
            "vehicle_id=%s, mqtt_username=%s",
            e, prefix, vehicle_id, mqtt_username
        )
        # Fallback to a default format
        structure_prefix = f"{prefix}/{mqtt_username}/{vehicle_id}"
        _LOGGER.debug("Using fallback structure prefix: %s", structure_prefix)

    _LOGGER.debug("Formatted structure prefix: %s", structure_prefix)
    return structure_prefix


def extract_vehicle_ids(topics, config):
    """Extract potential vehicle IDs from discovered topics."""
    _LOGGER.debug("Extracting potential vehicle IDs from %d topics", len(topics))
    potential_ids = set()
    discovered_username = None

    # Get the topic prefix
    prefix = config.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX) or DEFAULT_TOPIC_PREFIX

    # More generic pattern to match various username formats for OVMS
    general_pattern = fr"^{re.escape(prefix)}/([^/]+)/([^/]+)/"
    _LOGGER.debug(
        "Using general pattern to extract vehicle IDs: %s",
        general_pattern
    )

    for topic in topics:
        match = re.match(general_pattern, topic)
        if match and len(match.groups()) > 1:
            username = match.group(1)
            vehicle_id = match.group(2)
            if vehicle_id not in ["client", "rr"]:
                _LOGGER.debug(
                    "Found potential vehicle ID '%s' with username '%s' from topic '%s'",
                    vehicle_id, username, topic
                )
                # Save the discovered username for future use
                discovered_username = username
                potential_ids.add(vehicle_id)

    # Update the MQTT username in config if discovered
    if discovered_username:
        current_username = config.get(CONF_MQTT_USERNAME, "")
        if current_username != discovered_username:
            _LOGGER.debug(
                "Updating MQTT username from '%s' to discovered '%s'",
                current_username, discovered_username
            )
            config[CONF_MQTT_USERNAME] = discovered_username

    _LOGGER.debug("Extracted %d potential vehicle IDs: %s", len(potential_ids), potential_ids)
    return potential_ids


async def discover_topics(hass: HomeAssistant, config):
    """Discover available OVMS topics on the broker."""
    topic_prefix = config.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
    log_prefix = f"Topic discovery for prefix {topic_prefix}"
    _LOGGER.debug("%s - Starting", log_prefix)

    # Initialize debug info for this test
    debug_info = {
        "topic_prefix": topic_prefix,
        "test_start_time": asyncio.get_event_loop().time(),
    }

    # Format the discovery topic
    discovery_topic = DISCOVERY_TOPIC.format(prefix=topic_prefix)
    _LOGGER.debug("%s - Using discovery topic: %s", log_prefix, discovery_topic)
    debug_info["discovery_topic"] = discovery_topic

    # Set up a test client
    client_id = f"ha_ovms_discovery_{uuid.uuid4().hex[:8]}"
    protocol = mqtt.MQTTv5 if hasattr(mqtt, 'MQTTv5') else mqtt.MQTTv311

    _LOGGER.debug("%s - Creating client with ID: %s", log_prefix, client_id)
    mqttc = mqtt.Client(client_id=client_id, protocol=protocol)

    discovered_topics = set()
    connection_status = {"connected": False, "rc": None}

    # Define callbacks
    def on_connect(_, __, flags, rc, _properties=None):
        """Handle connection result."""
        connection_status["connected"] = rc == 0
        connection_status["rc"] = rc
        connection_status["timestamp"] = asyncio.get_event_loop().time()

        _LOGGER.debug("%s - Connection callback: rc=%s, flags=%s", log_prefix, rc, flags)

        if rc == 0:
            _LOGGER.debug(
                "%s - Subscribing to discovery topic: %s",
                log_prefix,
                discovery_topic
            )
            mqttc.subscribe(discovery_topic, qos=config.get(CONF_QOS, 1))

    def on_message(_, __, msg):
        """Handle incoming messages."""
        _LOGGER.debug(
            "%s - Message received on topic: %s (payload len: %d)",
            log_prefix, msg.topic, len(msg.payload)
        )
        discovered_topics.add(msg.topic)

    def on_disconnect(_, __, rc, _properties=None):
        """Handle disconnection."""
        connection_status["connected"] = False
        connection_status["disconnect_rc"] = rc
        connection_status["disconnect_timestamp"] = asyncio.get_event_loop().time()
        _LOGGER.debug("%s - Disconnected with result code: %s", log_prefix, rc)

    def on_log(_, __, ___, buf):
        """Log MQTT client internal messages."""
        _LOGGER.debug("%s - MQTT Log: %s", log_prefix, buf)

    # Configure the client
    if hasattr(mqtt, 'MQTTv5'):
        mqttc.on_connect = on_connect
    else:
        # For MQTT v3.1.1
        def on_connect_v311(client, userdata, flags, rc):
            on_connect(client, userdata, flags, rc, None)
        mqttc.on_connect = on_connect_v311

    mqttc.on_message = on_message
    mqttc.on_disconnect = on_disconnect
    mqttc.on_log = on_log

    if CONF_USERNAME in config and config[CONF_USERNAME]:
        _LOGGER.debug("%s - Setting username: %s", log_prefix, config[CONF_USERNAME])
        mqttc.username_pw_set(
            username=config[CONF_USERNAME],
            password=config[CONF_PASSWORD] if CONF_PASSWORD in config else None,
        )

    if config[CONF_PORT] == 8883:
        verify_ssl = config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
        try:
            # Use executor to avoid blocking the event loop
            context = await hass.async_add_executor_job(ssl.create_default_context)
            # Allow self-signed certificates if verification is disabled
            if not verify_ssl:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            mqttc.tls_set_context(context)
            debug_info["tls_enabled"] = True
            debug_info["tls_verify"] = verify_ssl
        except ssl.SSLError as ssl_err:
            _LOGGER.error("%s - SSL/TLS setup error: %s", log_prefix, ssl_err)
            debug_info["ssl_error"] = str(ssl_err)
            return {
                "success": False,
                "error_type": ERROR_CANNOT_CONNECT,
                "message": f"SSL/TLS Error: {ssl_err}",
            }

    # Set up connection timeout
    mqttc.connect_timeout = 5.0

    try:
        # Connect to the broker
        _LOGGER.debug("%s - Connecting to broker", log_prefix)
        await hass.async_add_executor_job(
            mqttc.connect,
            config[CONF_HOST],
            config[CONF_PORT],
            60,  # Keep alive timeout
        )

        # Start the loop in a separate thread
        mqttc.loop_start()

        # Wait for connection to establish
        connected = False
        for i in range(10):  # Try for up to 5 seconds
            if connection_status.get("connected"):
                connected = True
                break
            await asyncio.sleep(0.5)
            _LOGGER.debug("%s - Waiting for connection (%d/10)", log_prefix, i+1)

        if not connected:
            mqttc.loop_stop()
            rc = connection_status.get("rc", "unknown")
            _LOGGER.error("%s - Connection failed, rc=%s", log_prefix, rc)
            return {
                "success": False,
                "error_type": ERROR_CANNOT_CONNECT,
                "message": f"Failed to connect to MQTT broker (rc={rc})",
            }

        # Wait for messages to arrive
        _LOGGER.debug("%s - Waiting for messages", log_prefix)
        await asyncio.sleep(3)  # Wait for up to 3 seconds

        # Try to publish a message to stimulate response
        try:
            _LOGGER.debug(
                "%s - Publishing test message to stimulate responses",
                log_prefix
            )
            command_id = uuid.uuid4().hex[:8]
            # Use a generic discovery command - this will be ignored if the structure is wrong
            # but might trigger responses from OVMS modules
            test_topic = f"{topic_prefix}/client/rr/command/{command_id}"
            test_payload = "stat"

            mqttc.publish(test_topic, test_payload, qos=config.get(CONF_QOS, 1))
            _LOGGER.debug("%s - Test message published to %s", log_prefix, test_topic)

            # Also try a more generic topic to catch any responding devices
            vehicle_id = config.get(CONF_VEHICLE_ID, "")
            if vehicle_id:
                alt_test_topic = (
                    f"{topic_prefix}/+/{vehicle_id}/client/rr/command/{command_id}"
                )
                mqttc.publish(
                    alt_test_topic,
                    test_payload,
                    qos=config.get(CONF_QOS, 1)
                )
                _LOGGER.debug(
                    "%s - Also testing alternative topic: %s",
                    log_prefix,
                    alt_test_topic
                )

            # Wait a bit longer for responses
            await asyncio.sleep(2)
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.warning("%s - Error publishing test message: %s", log_prefix, ex)
            _LOGGER.debug(
                "%s - Test message error details: %s",
                log_prefix,
                traceback.format_exc()
            )

        # Clean up
        mqttc.loop_stop()
        try:
            mqttc.disconnect()
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.debug("%s - Error disconnecting: %s", log_prefix, ex)

        # Return the results
        topics_count = len(discovered_topics)

        debug_info["topics_count"] = topics_count
        debug_info["discovered_topics"] = list(discovered_topics) if \
            len(discovered_topics) < 50 else list(discovered_topics)[:50]

        _LOGGER.debug(
            "%s - Discovery complete. Found %d topics: %s",
            log_prefix, topics_count, list(discovered_topics)[:10]
        )

        return {
            "success": True,
            "discovered_topics": discovered_topics,
            "topic_count": topics_count,
            "debug_info": debug_info,
        }

    except socket.timeout:
        _LOGGER.error("%s - Connection timeout", log_prefix)
        return {
            "success": False,
            "error_type": ERROR_TIMEOUT,
            "message": "Connection timeout during topic discovery",
        }
    except socket.error as socket_err:
        _LOGGER.error("%s - Connection error: %s", log_prefix, socket_err)
        _LOGGER.debug(
            "%s - Connection error details: %s",
            log_prefix,
            traceback.format_exc()
        )
        return {
            "success": False,
            "error_type": ERROR_CANNOT_CONNECT,
            "message": f"Connection error during topic discovery: {socket_err}",
        }
    except ConnectionError as conn_ex:
        _LOGGER.error("%s - Connection error: %s", log_prefix, conn_ex)
        _LOGGER.debug(
            "%s - Connection error details: %s",
            log_prefix,
            traceback.format_exc()
        )
        return {
            "success": False,
            "error_type": ERROR_CANNOT_CONNECT,
            "message": f"Connection error during topic discovery: {conn_ex}",
        }
    except TimeoutError as timeout_ex:
        _LOGGER.error("%s - Timeout error: %s", log_prefix, timeout_ex)
        _LOGGER.debug(
            "%s - Timeout error details: %s",
            log_prefix,
            traceback.format_exc()
        )
        return {
            "success": False,
            "error_type": ERROR_TIMEOUT,
            "message": f"Timeout error during topic discovery: {timeout_ex}",
        }
    except OSError as os_ex:
        _LOGGER.error("%s - OS error: %s", log_prefix, os_ex)
        _LOGGER.debug("%s - OS error details: %s", log_prefix, traceback.format_exc())
        return {
            "success": False,
            "error_type": ERROR_CANNOT_CONNECT,
            "message": f"OS error during topic discovery: {os_ex}",
        }
    except Exception as ex:  # pylint: disable=broad-except
        _LOGGER.error("%s - MQTT error: %s", log_prefix, ex)
        _LOGGER.debug("%s - MQTT error details: %s", log_prefix, traceback.format_exc())
        return {
            "success": False,
            "error_type": ERROR_UNKNOWN,
            "message": f"Error during topic discovery: {ex}",
        }


async def test_topic_availability(hass: HomeAssistant, config):
    """Test if the OVMS topics are available for a specific vehicle."""
    # Get constants
    from ..const import (
        TOPIC_TEMPLATE,
        COMMAND_TOPIC_TEMPLATE,
        RESPONSE_TOPIC_TEMPLATE
    )

    vehicle_id = config[CONF_VEHICLE_ID]
    log_prefix = f"Topic availability test for vehicle {vehicle_id}"
    _LOGGER.debug("%s - Starting", log_prefix)

    # Format the structure prefix for this vehicle
    structure_prefix = format_structure_prefix(config)

    # Initialize debug info for this test
    debug_info = {
        "vehicle_id": vehicle_id,
        "structure_prefix": structure_prefix,
        "test_start_time": asyncio.get_event_loop().time(),
    }

    # Format the topic template
    topic = TOPIC_TEMPLATE.format(structure_prefix=structure_prefix)
    _LOGGER.debug("%s - Using subscription topic: %s", log_prefix, topic)
    debug_info["subscription_topic"] = topic

    # Format command and response topics for request-response test
    command_id = uuid.uuid4().hex[:8]
    command_topic = COMMAND_TOPIC_TEMPLATE.format(
        structure_prefix=structure_prefix,
        command_id=command_id
    )
    response_topic = RESPONSE_TOPIC_TEMPLATE.format(
        structure_prefix=structure_prefix,
        command_id=command_id
    )

    _LOGGER.debug("%s - Using command topic: %s", log_prefix, command_topic)
    _LOGGER.debug("%s - Using response topic: %s", log_prefix, response_topic)

    debug_info["command_topic"] = command_topic
    debug_info["response_topic"] = response_topic

    # Set up a test client
    client_id = f"ha_ovms_topic_test_{uuid.uuid4().hex[:8]}"
    protocol = mqtt.MQTTv5 if hasattr(mqtt, 'MQTTv5') else mqtt.MQTTv311

    _LOGGER.debug("%s - Creating client with ID: %s", log_prefix, client_id)
    mqttc = mqtt.Client(client_id=client_id, protocol=protocol)

    messages_received = []
    topics_found = set()
    connection_status = {"connected": False, "rc": None}
    responses_received = []

    # Define callbacks
    def on_connect(_, __, flags, rc, _properties=None):
        """Handle connection result."""
        connection_status["connected"] = rc == 0
        connection_status["rc"] = rc
        connection_status["timestamp"] = asyncio.get_event_loop().time()

        _LOGGER.debug("%s - Connection callback: rc=%s, flags=%s", log_prefix, rc, flags)

        if rc == 0:
            # Subscribe to general topics and response topic
            _LOGGER.debug("%s - Subscribing to general topic: %s", log_prefix, topic)
            mqttc.subscribe(topic, qos=config.get(CONF_QOS, 1))

            _LOGGER.debug(
                "%s - Subscribing to response topic: %s",
                log_prefix,
                response_topic
            )
            mqttc.subscribe(response_topic, qos=config.get(CONF_QOS, 1))

            # Also try a direct subscription to known topic patterns
            prefix = config.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
            if prefix:
                # Try with the actual username instead of placeholder
                mqtt_username = config.get(CONF_MQTT_USERNAME, "")
                if mqtt_username:
                    direct_topic = f"{prefix}/{mqtt_username}/{vehicle_id}/#"
                    _LOGGER.debug(
                        "%s - Also subscribing to direct topic: %s",
                        log_prefix, direct_topic
                    )
                    mqttc.subscribe(
                        direct_topic,
                        qos=config.get(CONF_QOS, 1)
                    )

                # Also try with the pattern matching any username
                alt_topic = f"{prefix}/+/{vehicle_id}/#"
                _LOGGER.debug(
                    "%s - Also subscribing to alternative topic: %s",
                    log_prefix, alt_topic
                )
                mqttc.subscribe(
                    alt_topic,
                    qos=config.get(CONF_QOS, 1)
                )

    def on_message(_, __, msg):
        """Handle incoming messages."""
        _LOGGER.debug(
            "%s - Message received on topic: %s (payload len: %d)",
            log_prefix, msg.topic, len(msg.payload)
        )

        message_info = {
            "topic": msg.topic,
            "payload_length": len(msg.payload),
            "timestamp": asyncio.get_event_loop().time(),
        }

        # Try to decode payload for logging
        try:
            payload_str = msg.payload.decode('utf-8')
            message_info["payload"] = payload_str
            _LOGGER.debug("%s - Payload: %s", log_prefix, payload_str)
        except UnicodeDecodeError:
            message_info["payload"] = "<binary data>"
            _LOGGER.debug("%s - Payload: <binary data>", log_prefix)

        # Track all messages
        messages_received.append(message_info)
        topics_found.add(msg.topic)

        # Check if this is a response to our command
        if msg.topic == response_topic:
            _LOGGER.debug("%s - Response received for command!", log_prefix)
            responses_received.append(message_info)

    def on_disconnect(_, __, rc, _properties=None):
        """Handle disconnection."""
        connection_status["connected"] = False
        connection_status["disconnect_rc"] = rc
        connection_status["disconnect_timestamp"] = asyncio.get_event_loop().time()
        _LOGGER.debug("%s - Disconnected with result code: %s", log_prefix, rc)

    def on_log(_, __, ___, buf):
        """Log MQTT client internal messages."""
        _LOGGER.debug("%s - MQTT Log: %s", log_prefix, buf)

    # Configure the client
    if hasattr(mqtt, 'MQTTv5'):
        mqttc.on_connect = on_connect
    else:
        # For MQTT v3.1.1
        def on_connect_v311(client, userdata, flags, rc):
            on_connect(client, userdata, flags, rc, None)
        mqttc.on_connect = on_connect_v311

    mqttc.on_message = on_message
    mqttc.on_disconnect = on_disconnect
    mqttc.on_log = on_log

    if CONF_USERNAME in config and config[CONF_USERNAME]:
        _LOGGER.debug("%s - Setting username: %s", log_prefix, config[CONF_USERNAME])
        mqttc.username_pw_set(
            username=config[CONF_USERNAME],
            password=config[CONF_PASSWORD] if CONF_PASSWORD in config else None,
        )

    if config[CONF_PROTOCOL] == "mqtts":
        _LOGGER.debug("%s - Enabling SSL/TLS for port 8883", log_prefix)
        verify_ssl = config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)

        try:
            # Use executor to avoid blocking the event loop
            context = await hass.async_add_executor_job(ssl.create_default_context)
            # Allow self-signed certificates if verification is disabled
            if not verify_ssl:
                _LOGGER.debug("%s - SSL certificate verification disabled", log_prefix)
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            mqttc.tls_set_context(context)
            debug_info["tls_enabled"] = True
            debug_info["tls_verify"] = verify_ssl
        except ssl.SSLError as ssl_err:
            _LOGGER.error("%s - SSL/TLS setup error: %s", log_prefix, ssl_err)
            debug_info["ssl_error"] = str(ssl_err)
            return {
                "success": False,
                "error_type": ERROR_CANNOT_CONNECT,
                "message": f"SSL/TLS Error: {ssl_err}",
                "details": f"SSL configuration failed: {ssl_err}",
                "debug_info": debug_info,
            }

    # Set up connection timeout
    mqttc.connect_timeout = 5.0

    try:
        # Connect to the broker
        _LOGGER.debug("%s - Connecting to broker", log_prefix)
        await hass.async_add_executor_job(
            mqttc.connect,
            config[CONF_HOST],
            config[CONF_PORT],
            60,  # Keep alive timeout
        )

        # Start the loop in a separate thread
        mqttc.loop_start()

        # Wait for connection to establish
        connected = False
        for i in range(10):  # Try for up to 5 seconds
            if connection_status.get("connected"):
                connected = True
                break
            await asyncio.sleep(0.5)
            _LOGGER.debug("%s - Waiting for connection (%d/10)", log_prefix, i+1)

        if not connected:
            mqttc.loop_stop()
            rc = connection_status.get("rc", "unknown")
            _LOGGER.error("%s - Connection failed, rc=%s", log_prefix, rc)
            return {
                "success": False,
                "error_type": ERROR_CANNOT_CONNECT,
                "message": f"Failed to connect to MQTT broker (rc={rc})",
                "details": f"Could not connect to broker for topic testing. Result code: {rc}",
                "debug_info": debug_info,
            }

        # Wait for some initial messages
        _LOGGER.debug("%s - Waiting for initial messages", log_prefix)
        for i in range(5):  # Wait for up to 2.5 seconds
            if messages_received:
                break
            _LOGGER.debug("%s - No messages yet (%d/5)", log_prefix, i+1)
            await asyncio.sleep(0.5)

        # Send a command to test request-response
        _LOGGER.debug("%s - Sending test command to: %s", log_prefix, command_topic)

        try:
            # Use 'stat' command which should work with OVMS
            mqttc.publish(command_topic, "stat", qos=config.get(CONF_QOS, 1))

            # Wait for a response
            _LOGGER.debug("%s - Waiting for command response", log_prefix)
            for i in range(10):  # Wait for up to 5 seconds
                if responses_received:
                    break
                _LOGGER.debug("%s - No response yet (%d/10)", log_prefix, i+1)
                await asyncio.sleep(0.5)

            if responses_received:
                _LOGGER.debug("%s - Command response received!", log_prefix)
            else:
                _LOGGER.debug("%s - No command response received", log_prefix)
        except ConnectionError as conn_ex:
            _LOGGER.warning(
                "%s - Connection error sending command: %s",
                log_prefix,
                conn_ex
            )
            _LOGGER.debug(
                "%s - Command error details: %s",
                log_prefix,
                traceback.format_exc()
            )
        except TimeoutError as timeout_ex:
            _LOGGER.warning(
                "%s - Timeout error sending command: %s",
                log_prefix,
                timeout_ex
            )
            _LOGGER.debug(
                "%s - Command error details: %s",
                log_prefix,
                traceback.format_exc()
            )
        except OSError as os_ex:
            _LOGGER.warning("%s - OS error sending command: %s", log_prefix, os_ex)
            _LOGGER.debug(
                "%s - Command error details: %s",
                log_prefix,
                traceback.format_exc()
            )
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.warning("%s - Error sending command: %s", log_prefix, ex)
            _LOGGER.debug(
                "%s - Command error details: %s",
                log_prefix,
                traceback.format_exc()
            )

        # Wait a bit longer for more messages to arrive
        if not messages_received:
            _LOGGER.debug("%s - No messages received, waiting longer", log_prefix)
            await asyncio.sleep(3)

        # Clean up
        mqttc.loop_stop()
        try:
            mqttc.disconnect()
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.debug("%s - Disconnect error (ignorable): %s", log_prefix, ex)

        # Check if we received any messages
        messages_count = len(messages_received)
        topics_count = len(topics_found)

        debug_info["messages_received"] = messages_count
        debug_info["topics_found"] = topics_count
        debug_info["topics_list"] = list(topics_found)
        debug_info["responses_received"] = len(responses_received)

        _LOGGER.debug(
            "%s - Test complete. Messages: %d, Topics: %d, Responses: %d",
            log_prefix, messages_count, topics_count, len(responses_received)
        )

        # Even if we didn't receive messages, we'll consider it a success with a warning
        # since MQTT topics might not have data immediately
        return {
            "success": True,
            "details": f"Found {messages_count} messages on {topics_count} topics",
            "debug_info": debug_info,
        }

    except socket.timeout:
        _LOGGER.error("%s - Connection timeout", log_prefix)
        debug_info["error"] = {
            "type": "timeout",
            "message": "Connection timeout",
        }
        return {
            "success": False,
            "error_type": ERROR_TIMEOUT,
            "message": "Connection timeout",
            "details": "Connection to MQTT broker timed out during topic testing",
            "debug_info": debug_info,
        }
    except socket.error as socket_err:
        _LOGGER.error("%s - Connection error: %s", log_prefix, socket_err)
        _LOGGER.debug(
            "%s - Connection error details: %s",
            log_prefix,
            traceback.format_exc()
        )
        debug_info["error"] = {
            "type": "socket",
            "message": str(socket_err),
        }
        return {
            "success": False,
            "error_type": ERROR_CANNOT_CONNECT,
            "message": f"Connection error: {socket_err}",
            "details": f"Socket error during topic testing: {socket_err}",
            "debug_info": debug_info,
        }
    except ConnectionError as conn_ex:
        _LOGGER.error("%s - Connection error: %s", log_prefix, conn_ex)
        _LOGGER.debug(
            "%s - Connection error details: %s",
            log_prefix,
            traceback.format_exc()
        )
        debug_info["error"] = {
            "type": "connection",
            "message": str(conn_ex),
        }
        return {
            "success": False,
            "error_type": ERROR_CANNOT_CONNECT,
            "message": f"Connection error: {conn_ex}",
            "details": f"Connection error during topic testing: {conn_ex}",
            "debug_info": debug_info,
        }
    except TimeoutError as timeout_ex:
        _LOGGER.error("%s - Timeout error: %s", log_prefix, timeout_ex)
        _LOGGER.debug(
            "%s - Timeout error details: %s",
            log_prefix,
            traceback.format_exc()
        )
        debug_info["error"] = {
            "type": "timeout",
            "message": str(timeout_ex),
        }
        return {
            "success": False,
            "error_type": ERROR_TIMEOUT,
            "message": f"Timeout error: {timeout_ex}",
            "details": f"Timeout error during topic testing: {timeout_ex}",
            "debug_info": debug_info,
        }
    except OSError as os_ex:
        _LOGGER.error("%s - OS error: %s", log_prefix, os_ex)
        _LOGGER.debug("%s - OS error details: %s", log_prefix, traceback.format_exc())
        debug_info["error"] = {
            "type": "os",
            "message": str(os_ex),
        }
        return {
            "success": False,
            "error_type": ERROR_CANNOT_CONNECT,
            "message": f"OS error: {os_ex}",
            "details": f"OS error during topic testing: {os_ex}",
            "debug_info": debug_info,
        }
    except Exception as ex:  # pylint: disable=broad-except
        _LOGGER.exception("%s - Unexpected error: %s", log_prefix, ex)
        _LOGGER.debug(
            "%s - Unexpected error details: %s",
            log_prefix,
            traceback.format_exc()
        )
        debug_info["error"] = {
            "type": "unexpected",
            "message": str(ex),
        }
        return {
            "success": False,
            "error_type": ERROR_UNKNOWN,
            "message": f"Unexpected error: {ex}",
            "details": f"An unexpected error occurred during topic testing: {ex}",
            "debug_info": debug_info,
        }
