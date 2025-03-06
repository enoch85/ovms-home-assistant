"""MQTT helper functions for OVMS integration."""
import asyncio
import json
import logging
import ssl
import socket
import uuid
import time
from typing import Any, Dict, Optional, Tuple, Union, Callable

import paho.mqtt.client as mqtt

from homeassistant.core import HomeAssistant
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_PROTOCOL,
    CONF_USERNAME,
)

from ..const import (
    CONF_QOS,
    CONF_VERIFY_SSL,
    DEFAULT_QOS,
    DEFAULT_VERIFY_SSL,
    LOGGER_NAME,
)
from .error_handler import (
    OVMSError,
    ConnectionError,
    AuthError,
    TimeoutError,
    TLSError,
)

_LOGGER = logging.getLogger(LOGGER_NAME)


def ensure_serializable(obj: Any) -> Any:
    """Ensure objects are JSON serializable.
    
    Args:
        obj: The object to make serializable
        
    Returns:
        A serializable version of the object
    """
    if isinstance(obj, dict):
        return {k: ensure_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [ensure_serializable(item) for item in obj]
    elif isinstance(obj, tuple):
        return [ensure_serializable(item) for item in obj]
    elif hasattr(obj, '__dict__'):  # Convert custom objects to dict
        return {k: ensure_serializable(v) for k, v in obj.__dict__.items() 
                if not k.startswith('_')}
    elif obj.__class__.__name__ == 'ReasonCodes':  # Handle MQTT ReasonCodes specifically
        try:
            return [int(code) for code in obj]  # Convert to list of integers
        except:
            return str(obj)   # Fall back to string representation
    else:
        return obj


async def create_mqtt_client(
    hass: HomeAssistant, 
    config: Dict[str, Any], 
    client_id: Optional[str] = None
) -> Tuple[mqtt.Client, Dict[str, Any]]:
    """Create and configure an MQTT client.
    
    Args:
        hass: HomeAssistant instance
        config: MQTT configuration
        client_id: Optional client ID to use
        
    Returns:
        Tuple of (mqtt_client, debug_info)
        
    Raises:
        ConnectionError: If the connection cannot be established
        AuthError: If authentication fails
        TimeoutError: If the connection times out
        TLSError: If there is an SSL/TLS error
    """
    # Use provided client ID or generate a random one
    client_id = client_id or f"ovms_mqtt_{uuid.uuid4().hex[:8]}"
    protocol = mqtt.MQTTv5 if hasattr(mqtt, 'MQTTv5') else mqtt.MQTTv311
    
    debug_info = {
        "client_id": client_id,
        "protocol": "MQTTv5" if hasattr(mqtt, 'MQTTv5') else "MQTTv311",
        "host": config.get(CONF_HOST),
        "port": config.get(CONF_PORT),
        "has_username": bool(config.get(CONF_USERNAME)),
    }
    
    _LOGGER.debug("Creating MQTT client with ID: %s and protocol: %s", 
                 client_id, debug_info["protocol"])
    
    # Create the client
    mqttc = mqtt.Client(client_id=client_id, protocol=protocol)
    
    # Configure authentication if provided
    if config.get(CONF_USERNAME):
        _LOGGER.debug("Setting username and password for MQTT client")
        mqttc.username_pw_set(
            username=config.get(CONF_USERNAME),
            password=config.get(CONF_PASSWORD)
        )
    
    # Configure TLS if needed
    if config.get(CONF_PORT) == 8883:
        _LOGGER.debug("Enabling SSL/TLS for port 8883")
        verify_ssl = config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
        try:
            # Use executor to avoid blocking the event loop
            context = await hass.async_add_executor_job(ssl.create_default_context)
            # Allow self-signed certificates if verification is disabled
            if not verify_ssl:
                _LOGGER.debug("SSL certificate verification disabled (insecure TLS/SSL allowed)")
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            mqttc.tls_set_context(context)
            debug_info["tls_enabled"] = True
            debug_info["tls_verify"] = verify_ssl
        except ssl.SSLError as err:
            raise TLSError(f"SSL/TLS setup error: {err}")
    
    return mqttc, debug_info


async def connect_mqtt_client(
    hass: HomeAssistant, 
    client: mqtt.Client, 
    config: Dict[str, Any], 
    on_connect: Optional[Callable] = None,
    on_disconnect: Optional[Callable] = None,
    timeout: int = 10
) -> None:
    """Connect an MQTT client to the broker.
    
    Args:
        hass: HomeAssistant instance
        client: MQTT client to connect
        config: MQTT configuration
        on_connect: Optional callback for successful connection
        on_disconnect: Optional callback for disconnection
        timeout: Connection timeout in seconds
        
    Raises:
        ConnectionError: If the connection cannot be established
        AuthError: If authentication fails
        TimeoutError: If the connection times out
    """
    host = config.get(CONF_HOST)
    port = config.get(CONF_PORT)
    
    # Set connection callbacks if provided
    if on_connect:
        client.on_connect = on_connect
    if on_disconnect:
        client.on_disconnect = on_disconnect
    
    # Set connection timeout
    client.connect_timeout = timeout
    
    try:
        # Try DNS resolution first with better error reporting
        try:
            await hass.async_add_executor_job(socket.gethostbyname, host)
        except socket.gaierror as err:
            _LOGGER.error("DNS resolution failed for host %s: %s", host, err)
            raise ConnectionError(f"DNS resolution failed: {err}")
        
        # Connect using the executor to avoid blocking
        await hass.async_add_executor_job(
            client.connect,
            host,
            port,
            60,  # Keep alive timeout
        )
        
        # Start the loop in a separate thread
        client.loop_start()
        
    except socket.timeout:
        _LOGGER.error("Connection timeout connecting to %s:%s", host, port)
        raise TimeoutError(f"Connection timeout connecting to {host}:{port}")
    except socket.error as err:
        _LOGGER.error("Socket error connecting to %s:%s: %s", host, port, err)
        raise ConnectionError(f"Socket error: {err}")
    except Exception as ex:
        # Check for auth errors specifically
        if "not authorised" in str(ex).lower() or "not authorized" in str(ex).lower():
            _LOGGER.error("Authorization failed connecting to MQTT broker: %s", ex)
            raise AuthError(f"Authorization failed: {ex}")
        
        _LOGGER.exception("Failed to connect to MQTT broker: %s", ex)
        raise ConnectionError(f"Connection error: {ex}")


async def wait_for_connected(
    client_connected_flag: "asyncio.Event", 
    timeout: int = 10
) -> None:
    """Wait for an MQTT client to connect to the broker.
    
    Args:
        client_connected_flag: Event that will be set when connected
        timeout: Maximum time to wait in seconds
        
    Raises:
        TimeoutError: If the connection times out
    """
    try:
        await asyncio.wait_for(client_connected_flag.wait(), timeout)
    except asyncio.TimeoutError:
        _LOGGER.error("Timed out waiting for MQTT connection")
        raise TimeoutError("Timed out waiting for MQTT connection")


async def test_topic_subscription(
    hass: HomeAssistant,
    mqtt_client: mqtt.Client,
    topic: str,
    qos: int = DEFAULT_QOS,
    timeout: int = 5,
) -> Dict[str, Any]:
    """Test if we can subscribe to a topic.
    
    Args:
        hass: HomeAssistant instance
        mqtt_client: Connected MQTT client
        topic: Topic to test subscription to
        qos: QoS level to use
        timeout: Maximum time to wait in seconds
        
    Returns:
        Dictionary with subscription result
    """
    subscription_result = {"success": False, "topic": topic}
    subscription_event = asyncio.Event()
    
    def on_subscribe(client, userdata, mid, granted_qos, properties=None):
        """Handle subscription result."""
        _LOGGER.debug("Subscription callback: mid=%s, qos=%s", mid, granted_qos)
        subscription_result["success"] = True
        subscription_result["granted_qos"] = granted_qos
        subscription_event.set()
    
    # Configure client callback
    if hasattr(mqtt, 'MQTTv5'):
        original_callback = mqtt_client.on_subscribe
        mqtt_client.on_subscribe = on_subscribe
    else:
        # For MQTT v3.1.1
        original_callback = mqtt_client.on_subscribe
        
        def on_subscribe_v311(client, userdata, mid, granted_qos):
            on_subscribe(client, userdata, mid, granted_qos, None)
        
        mqtt_client.on_subscribe = on_subscribe_v311
    
    try:
        _LOGGER.debug("Subscribing to test topic: %s", topic)
        result = mqtt_client.subscribe(topic, qos=qos)
        subscription_result["subscribe_result"] = ensure_serializable(result)
        
        try:
            # Wait for the subscription event with timeout
            await asyncio.wait_for(subscription_event.wait(), timeout)
            
            if subscription_result.get("success"):
                _LOGGER.debug("Subscription successful: %s", topic)
                return {"success": True, "topic": topic}
            else:
                return {
                    "success": False,
                    "message": "Subscription not confirmed by broker",
                    "topic": topic,
                }
                
        except asyncio.TimeoutError:
            _LOGGER.error("Subscription timed out: %s", topic)
            return {
                "success": False,
                "message": "Subscription timed out",
                "topic": topic,
            }
            
    except Exception as ex:
        _LOGGER.exception("Subscription error: %s", ex)
        return {
            "success": False,
            "message": f"Subscription error: {ex}",
            "topic": topic,
        }
    finally:
        # Restore original callback
        mqtt_client.on_subscribe = original_callback


async def test_mqtt_broker(
    hass: HomeAssistant, 
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """Test if we can connect to the MQTT broker.
    
    Args:
        hass: HomeAssistant instance
        config: MQTT broker configuration
        
    Returns:
        Dictionary with test results
    """
    debug_info = {}
    
    try:
        _LOGGER.debug("Testing MQTT broker connection")
        
        # Create a test client
        client_id = f"ovms_test_{uuid.uuid4().hex[:8]}"
        client, client_debug = await create_mqtt_client(hass, config, client_id)
        debug_info.update(client_debug)
        
        # Set up connection status
        connection_status = {"connected": False, "rc": None}
        connected_event = asyncio.Event()
        
        def on_connect(client, userdata, flags, rc, properties=None):
            """Handle connection result."""
            connection_status["connected"] = (rc == 0)
            connection_status["rc"] = rc
            connection_status["timestamp"] = time.time()
            
            if rc == 0:
                connected_event.set()
            
        def on_disconnect(client, userdata, rc, properties=None):
            """Handle disconnection."""
            connection_status["connected"] = False
            connection_status["disconnect_rc"] = rc
            connection_status["disconnect_timestamp"] = time.time()
            
        # Set up callbacks
        if hasattr(mqtt, 'MQTTv5'):
            client.on_connect = on_connect
        else:
            # For MQTT v3.1.1
            def on_connect_v311(client, userdata, flags, rc):
                on_connect(client, userdata, flags, rc, None)
            client.on_connect = on_connect_v311
        
        client.on_disconnect = on_disconnect
        
        # Connect to the broker
        await connect_mqtt_client(hass, client, config)
        
        # Wait for the connection to establish
        try:
            await asyncio.wait_for(connected_event.wait(), 5)
            
            # Test subscribing to a topic
            test_topic = f"homeassistant/{client_id}/test"
            subscription_result = await test_topic_subscription(hass, client, test_topic)
            debug_info["subscription_test"] = subscription_result
            
            # Clean up
            client.loop_stop()
            try:
                client.disconnect()
            except Exception:
                pass
            
            return {
                "success": True,
                "details": "Connection and subscription tests passed successfully",
                "debug_info": debug_info,
            }
            
        except asyncio.TimeoutError:
            client.loop_stop()
            return {
                "success": False,
                "error_type": "timeout",
                "message": "Connection timeout",
                "debug_info": debug_info,
            }
            
    except OVMSError as err:
        return {
            "success": False,
            "error_type": err.error_type,
            "message": str(err),
            "debug_info": debug_info,
        }
    except Exception as ex:
        _LOGGER.exception("Unexpected error in MQTT broker test: %s", ex)
        return {
            "success": False,
            "error_type": "unknown",
            "message": f"Unexpected error: {ex}",
            "debug_info": debug_info,
        }
