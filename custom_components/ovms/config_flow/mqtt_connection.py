"""MQTT connection handling for OVMS configuration."""

import asyncio
import logging
import socket
import ssl
import time
import traceback
import uuid
from typing import Dict, Any, Optional

import paho.mqtt.client as mqtt

from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    CONF_PROTOCOL,
)
from homeassistant.core import HomeAssistant

from ..const import (
    CONF_QOS,
    CONF_VERIFY_SSL,
    DEFAULT_QOS,
    DEFAULT_VERIFY_SSL,
    LOGGER_NAME,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_AUTH,
    ERROR_TIMEOUT,
    ERROR_TOPIC_ACCESS_DENIED,
    ERROR_TLS_ERROR,
    ERROR_UNKNOWN,
)

_LOGGER = logging.getLogger(LOGGER_NAME)


def ensure_serializable(obj):
    """Ensure objects are JSON serializable."""
    if isinstance(obj, dict):
        return {k: ensure_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [ensure_serializable(item) for item in obj]
    if isinstance(obj, tuple):
        return [ensure_serializable(item) for item in obj]
    if hasattr(obj, "__dict__"):
        return {
            k: ensure_serializable(v)
            for k, v in obj.__dict__.items()
            if not k.startswith("_")
        }
    if obj.__class__.__name__ == "ReasonCodes":
        try:
            return [int(code) for code in obj]
        except (ValueError, TypeError):
            return str(obj)
    return obj


async def test_mqtt_connection(
    hass: HomeAssistant, config
):  # pylint: disable=too-many-locals,too-many-branches,too-many-statements,too-many-return-statements
    """Test if we can connect to the MQTT broker."""
    log_prefix = f"MQTT connection test to {config[CONF_HOST]}:{config[CONF_PORT]}"
    _LOGGER.debug("%s - Starting", log_prefix)

    # Initialize debug info for this test
    debug_info = {
        "host": config[CONF_HOST],
        "port": config[CONF_PORT],
        "protocol": config[CONF_PROTOCOL],
        "has_username": bool(config.get(CONF_USERNAME)),
        "test_start_time": asyncio.get_event_loop().time(),
    }

    # Generate a random client ID for this connection test
    client_id = f"ha_ovms_{uuid.uuid4().hex[:8]}"
    protocol = mqtt.MQTTv5 if hasattr(mqtt, "MQTTv5") else mqtt.MQTTv311

    debug_info["mqtt_protocol_version"] = (
        "MQTTv5" if hasattr(mqtt, "MQTTv5") else "MQTTv311"
    )

    _LOGGER.debug(
        "%s - Creating client with ID: %s and protocol: %s",
        log_prefix,
        client_id,
        debug_info["mqtt_protocol_version"],
    )

    mqttc = mqtt.Client(client_id=client_id, protocol=protocol)

    # Set up connection status for debugging
    connection_status = {"connected": False, "rc": None, "flags": None}

    # Define callback for debugging
    def on_connect(_, __, flags, rc, _properties=None):
        """Handle connection result."""
        connection_status["connected"] = rc == 0
        connection_status["rc"] = rc
        connection_status["flags"] = flags
        # Using time.time() instead of asyncio.get_event_loop().time()
        connection_status["timestamp"] = time.time()

        _LOGGER.debug(
            "%s - Connection callback: rc=%s, flags=%s", log_prefix, rc, flags
        )

    def on_disconnect(_, __, rc, _properties=None):
        """Handle disconnection."""
        connection_status["connected"] = False
        connection_status["disconnect_rc"] = rc
        # Using time.time() instead of asyncio.get_event_loop().time()
        connection_status["disconnect_timestamp"] = time.time()
        _LOGGER.debug("%s - Disconnected with result code: %s", log_prefix, rc)

    def on_log(_, __, ___, buf):
        """Log MQTT client internal messages."""
        _LOGGER.debug("%s - MQTT Log: %s", log_prefix, buf)

    # Configure client callbacks
    if hasattr(mqtt, "MQTTv5"):
        mqttc.on_connect = on_connect
    else:
        # For MQTT v3.1.1
        def on_connect_v311(client, userdata, flags, rc):
            on_connect(client, userdata, flags, rc, None)

        mqttc.on_connect = on_connect_v311

    mqttc.on_disconnect = on_disconnect
    mqttc.on_log = on_log

    if CONF_USERNAME in config and config[CONF_USERNAME]:
        _LOGGER.debug("%s - Setting username: %s", log_prefix, config[CONF_USERNAME])
        mqttc.username_pw_set(
            username=config[CONF_USERNAME],
            password=config[CONF_PASSWORD] if CONF_PASSWORD in config else None,
        )

    if config[CONF_PORT] == 8883:
        _LOGGER.debug("%s - Enabling SSL/TLS for port 8883", log_prefix)
        verify_ssl = config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
        try:
            # Use executor to avoid blocking the event loop
            context = await hass.async_add_executor_job(ssl.create_default_context)
            # Allow self-signed certificates if insecure is allowed
            if not verify_ssl:
                _LOGGER.debug(
                    "%s - SSL certificate verification disabled (insecure TLS/SSL allowed)",
                    log_prefix,
                )
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
                "error_type": ERROR_TLS_ERROR,
                "message": f"SSL/TLS Error: {ssl_err}",
                "details": f"SSL configuration failed: {ssl_err}",
            }

    # Set up connection timeout
    mqttc.connect_timeout = 5.0
    debug_info["connect_timeout"] = 5.0

    try:
        # DNS resolution check
        _LOGGER.debug("%s - Resolving hostname", log_prefix)
        dns_start = asyncio.get_event_loop().time()
        try:
            socket.gethostbyname(config[CONF_HOST])
            dns_success = True
            dns_error = None
        except socket.gaierror as err:
            dns_success = False
            dns_error = str(err)
        dns_time = asyncio.get_event_loop().time() - dns_start

        debug_info["dns_resolution"] = {
            "success": dns_success,
            "time_taken": dns_time,
        }

        if not dns_success:
            _LOGGER.error("%s - DNS resolution failed: %s", log_prefix, dns_error)
            debug_info["dns_resolution"]["error"] = dns_error
            return {
                "success": False,
                "error_type": ERROR_CANNOT_CONNECT,
                "message": f"DNS resolution failed: {dns_error}",
                "details": (
                    f"Could not resolve hostname '{config[CONF_HOST]}': " f"{dns_error}"
                ),
            }

        # Port check
        _LOGGER.debug("%s - Checking if port is open", log_prefix)
        port_check_start = asyncio.get_event_loop().time()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        try:
            port_result = s.connect_ex((config[CONF_HOST], config[CONF_PORT]))
            port_open = port_result == 0
        except socket.error:
            port_open = False
        finally:
            s.close()
        port_check_time = asyncio.get_event_loop().time() - port_check_start

        debug_info["port_check"] = {
            "success": port_open,
            "time_taken": port_check_time,
        }

        if not port_open:
            _LOGGER.error(
                "%s - Port check failed, port %d is closed",
                log_prefix,
                config[CONF_PORT],
            )
            debug_info["port_check"]["error"] = f"Port {config[CONF_PORT]} is closed"
            return {
                "success": False,
                "error_type": ERROR_CANNOT_CONNECT,
                "message": f"Port {config[CONF_PORT]} is closed",
                "details": (
                    f"Port {config[CONF_PORT]} on host '{config[CONF_HOST]}' "
                    f"is not open."
                ),
            }

        # Now try the actual MQTT connection
        _LOGGER.debug("%s - Connecting to broker", log_prefix)
        connect_start = asyncio.get_event_loop().time()

        # Connect using the executor to avoid blocking
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
            _LOGGER.debug("%s - Waiting for connection (%d/10)", log_prefix, i + 1)
            if connection_status.get("connected"):
                connected = True
                break
            if (
                connection_status.get("rc") is not None
                and connection_status.get("rc") != 0
            ):
                # Connection failed with specific error code
                break
            await asyncio.sleep(0.5)

        connect_time = asyncio.get_event_loop().time() - connect_start
        debug_info["mqtt_connect"] = {
            "success": connected,
            "time_taken": connect_time,
            "status": ensure_serializable(connection_status),
        }

        mqttc.loop_stop()

        if connected:
            _LOGGER.debug("%s - Connection successful", log_prefix)
            # Test subscribing to a topic as a further check
            _LOGGER.debug("%s - Testing topic subscription", log_prefix)
            sub_result = await test_subscription(hass, mqttc, config, client_id)
            debug_info["subscription_test"] = ensure_serializable(sub_result)

            if not sub_result["success"]:
                try:
                    mqttc.disconnect()
                except Exception:  # pylint: disable=broad-except
                    pass

                # Prepare detailed error message
                error_topic = sub_result.get("topic", "unknown")
                error_details_text = sub_result.get(
                    "details", "Could not subscribe to test topics"
                )

                return {
                    "success": False,
                    "error_type": ERROR_TOPIC_ACCESS_DENIED,
                    "message": f"Topic subscription test failed for {error_topic}",
                    "details": (
                        f"Access denied to the test topic '{error_topic}'. This is "
                        f"likely due to MQTT ACL (Access Control List) restrictions. "
                        f"For EMQX broker, ensure the user has 'Subscribe' permission "
                        f"for '{error_topic}' or 'homeassistant/#' wildcard topic. "
                        f"{error_details_text}"
                    ),
                }

            try:
                mqttc.disconnect()
            except Exception:  # pylint: disable=broad-except
                pass
            return {
                "success": True,
                "details": "Connection and subscription tests passed successfully",
                "debug_info": debug_info,
            }

        error_message = "Failed to connect"
        error_type = ERROR_CANNOT_CONNECT
        details = "Could not establish connection to the MQTT broker"

        # Check for specific connection issues
        rc = connection_status.get("rc")
        if rc is not None:
            if rc == 1:
                error_message = "Connection refused - incorrect protocol version"
            elif rc == 2:
                error_message = "Connection refused - invalid client identifier"
            elif rc == 3:
                error_message = "Connection refused - server unavailable"
            elif rc == 4:
                error_message = "Connection refused - bad username or password"
                error_type = ERROR_INVALID_AUTH
                details = (
                    "Authentication failed. Please check your username and password."
                )
            elif rc == 5:
                error_message = "Connection refused - not authorized"
                error_type = ERROR_INVALID_AUTH
                details = (
                    "Not authorized to connect. Check your credentials and permissions."
                )

        _LOGGER.error("%s - %s (rc=%s)", log_prefix, error_message, rc)
        debug_info["error"] = {
            "message": error_message,
            "rc": rc,
        }

        return {
            "success": False,
            "error_type": error_type,
            "message": error_message,
            "details": details,
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
            "details": (
                f"Connection to {config[CONF_HOST]}:{config[CONF_PORT]} "
                f"timed out after {mqttc.connect_timeout} seconds"
            ),
            "debug_info": debug_info,
        }
    # Handling exception order correctly
    except ConnectionError as conn_ex:
        _LOGGER.error("%s - Connection error: %s", log_prefix, conn_ex)
        _LOGGER.debug(
            "%s - Connection error details: %s", log_prefix, traceback.format_exc()
        )
        debug_info["error"] = {
            "type": "connection",
            "message": str(conn_ex),
        }
        return {
            "success": False,
            "error_type": ERROR_CANNOT_CONNECT,
            "message": f"Connection error: {conn_ex}",
            "details": f"Connection error: {conn_ex}",
            "debug_info": debug_info,
        }
    except TimeoutError as timeout_ex:
        _LOGGER.error("%s - Timeout error: %s", log_prefix, timeout_ex)
        _LOGGER.debug(
            "%s - Timeout error details: %s", log_prefix, traceback.format_exc()
        )
        debug_info["error"] = {
            "type": "timeout",
            "message": str(timeout_ex),
        }
        return {
            "success": False,
            "error_type": ERROR_TIMEOUT,
            "message": f"Timeout error: {timeout_ex}",
            "details": f"Timeout error: {timeout_ex}",
            "debug_info": debug_info,
        }
    except socket.error as socket_err:
        _LOGGER.error("%s - Socket error: %s", log_prefix, socket_err)
        _LOGGER.debug(
            "%s - Socket error details: %s", log_prefix, traceback.format_exc()
        )
        debug_info["error"] = {
            "type": "socket",
            "message": str(socket_err),
        }
        return {
            "success": False,
            "error_type": ERROR_CANNOT_CONNECT,
            "message": f"Socket error: {socket_err}",
            "details": f"Socket error when connecting: {socket_err}",
            "debug_info": debug_info,
        }
    except Exception as ex:  # pylint: disable=broad-except
        _LOGGER.exception("%s - Unexpected error: %s", log_prefix, ex)
        _LOGGER.debug(
            "%s - Unexpected error details: %s", log_prefix, traceback.format_exc()
        )
        error_type = ERROR_UNKNOWN

        if "failed to connect" in str(ex).lower():
            error_type = ERROR_CANNOT_CONNECT
        if "not authorised" in str(ex).lower() or "not authorized" in str(ex).lower():
            error_type = ERROR_INVALID_AUTH

        debug_info["error"] = {
            "type": "unexpected",
            "message": str(ex),
        }
        return {
            "success": False,
            "error_type": error_type,
            "message": f"MQTT Error: {ex}",
            "details": f"An unexpected error occurred: {ex}",
            "debug_info": debug_info,
        }


async def test_subscription(
    hass, mqtt_client, config, client_id
):  # pylint: disable=too-many-locals
    """Test if we can subscribe to a topic."""
    log_prefix = f"MQTT subscription test for {config[CONF_HOST]}:{config[CONF_PORT]}"

    # Use a test topic that should be accessible to all users
    test_topic = f"homeassistant/{client_id}/test"
    qos = config.get(CONF_QOS, DEFAULT_QOS)

    subscription_result = {"success": False, "topic": test_topic}

    # Define callback for subscription
    def on_subscribe(_, __, mid, granted_qos, _properties=None):
        """Handle subscription result."""
        _LOGGER.debug(
            "%s - Subscription callback: mid=%s, qos=%s", log_prefix, mid, granted_qos
        )
        subscription_result["success"] = True
        subscription_result["granted_qos"] = granted_qos

    # Configure client callback
    if hasattr(mqtt, "MQTTv5"):
        mqtt_client.on_subscribe = on_subscribe
    else:
        # For MQTT v3.1.1
        def on_subscribe_v311(client, userdata, mid, granted_qos):
            on_subscribe(client, userdata, mid, granted_qos, None)

        mqtt_client.on_subscribe = on_subscribe_v311

    try:
        _LOGGER.debug("%s - Subscribing to test topic: %s", log_prefix, test_topic)
        result = mqtt_client.subscribe(test_topic, qos=qos)
        subscription_result["subscribe_result"] = ensure_serializable(result)

        # Check if subscription was initiated successfully
        if result and result[0] == 0:  # MQTT_ERR_SUCCESS
            # Successful subscription initiation, assume it worked
            _LOGGER.debug("%s - Subscription initiated successfully", log_prefix)
            return {"success": True, "topic": test_topic}

        # Wait for subscription confirmation via callback
        subscription_confirmed = False
        for i in range(5):  # Try for up to 2.5 seconds
            if subscription_result.get("success"):
                subscription_confirmed = True
                break
            await asyncio.sleep(0.5)
            _LOGGER.debug(
                "%s - Waiting for subscription confirmation (%d/5)", log_prefix, i + 1
            )

        if subscription_confirmed:
            _LOGGER.debug("%s - Subscription successful", log_prefix)
            return {"success": True, "topic": test_topic}

        _LOGGER.error("%s - Subscription not confirmed", log_prefix)
        return {
            "success": False,
            "message": "Subscription request was not confirmed by the broker",
            "topic": test_topic,
            "details": (
                "The MQTT broker did not confirm the subscription request. "
                "This may be due to ACL rules on the broker preventing subscription to the "
                "test topic, connectivity issues, or broker configuration. "
                "Check the broker's logs and access control settings."
            ),
        }

    # Correct exception order
    except ConnectionError as conn_ex:
        _LOGGER.exception("%s - Connection error: %s", log_prefix, conn_ex)
        _LOGGER.debug(
            "%s - Connection error details: %s", log_prefix, traceback.format_exc()
        )
        return {
            "success": False,
            "message": f"Connection error: {conn_ex}",
            "topic": test_topic,
            "details": f"Connection error during subscription: {conn_ex}",
        }
    except TimeoutError as timeout_ex:
        _LOGGER.exception("%s - Timeout error: %s", log_prefix, timeout_ex)
        _LOGGER.debug(
            "%s - Timeout error details: %s", log_prefix, traceback.format_exc()
        )
        return {
            "success": False,
            "message": f"Timeout error: {timeout_ex}",
            "topic": test_topic,
            "details": f"Timeout error during subscription: {timeout_ex}",
        }
    except Exception as ex:  # pylint: disable=broad-except
        _LOGGER.exception("%s - Subscription error: %s", log_prefix, ex)
        _LOGGER.debug(
            "%s - Subscription error details: %s", log_prefix, traceback.format_exc()
        )
        return {
            "success": False,
            "message": f"Subscription error: {ex}",
            "topic": test_topic,
            "details": (
                f"Error while attempting to subscribe to the test topic "
                f"'{test_topic}'. Check your broker connection and permissions. "
                f"Full error: {ex}"
            ),
        }
