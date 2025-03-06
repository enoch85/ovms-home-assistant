"""Config flow for OVMS integration."""
import asyncio
import logging
import ssl
import socket
import uuid
import time
import re
import hashlib
from typing import Any, Dict, Optional, Callable, Tuple
from contextlib import contextmanager

import voluptuous as vol
import paho.mqtt.client as mqtt

from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    CONF_PROTOCOL,
)
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONFIG_VERSION,
    DEFAULT_PORT,
    DEFAULT_QOS,
    DEFAULT_PROTOCOL,
    DEFAULT_TOPIC_PREFIX,
    DEFAULT_TOPIC_STRUCTURE,
    DEFAULT_VERIFY_SSL,
    CONF_VEHICLE_ID,
    CONF_QOS,
    CONF_TOPIC_PREFIX,
    CONF_MQTT_USERNAME,
    CONF_TOPIC_STRUCTURE,
    CONF_VERIFY_SSL,
    CONF_ORIGINAL_VEHICLE_ID,
    PROTOCOLS,
    TOPIC_STRUCTURES,
    LOGGER_NAME,
    DISCOVERY_TOPIC,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_AUTH,
    ERROR_TIMEOUT,
    ERROR_INVALID_RESPONSE,
    ERROR_NO_TOPICS,
    ERROR_TOPIC_ACCESS_DENIED,
    ERROR_TLS_ERROR,
    ERROR_UNKNOWN,
)

_LOGGER = logging.getLogger(LOGGER_NAME)


class OVMSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OVMS."""

    VERSION = CONFIG_VERSION
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    def __init__(self):
        """Initialize the OVMS config flow."""
        self.mqtt_config = {}
        self.debug_info = {}
        self.discovered_topics = set()

    def _ensure_serializable(self, obj):
        """Convert MQTT objects to serializable types."""
        if isinstance(obj, dict):
            return {k: self._ensure_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._ensure_serializable(item) for item in obj]
        elif isinstance(obj, tuple):
            return [self._ensure_serializable(item) for item in obj]
        elif hasattr(obj, '__dict__'):
            return {k: self._ensure_serializable(v) for k, v in obj.__dict__.items() 
                    if not k.startswith('_')}
        elif obj.__class__.__name__ == 'ReasonCodes':
            try:
                return [int(code) for code in obj]
            except:
                return str(obj)
        else:
            return obj

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            _LOGGER.debug("Starting OVMS MQTT broker setup: %s", user_input)
            self.debug_info["broker_setup_start"] = time.time()
            
            # Extract protocol and port from Port selection
            if "Port" in user_input:
                if user_input["Port"] == "mqtts":
                    user_input[CONF_PROTOCOL] = "mqtts"
                    user_input[CONF_PORT] = 8883
                    # Handle the inverted SSL verification setting
                    if "allow_insecure_ssl" in user_input:
                        user_input[CONF_VERIFY_SSL] = not user_input["allow_insecure_ssl"]
                        del user_input["allow_insecure_ssl"]
                    else:
                        user_input[CONF_VERIFY_SSL] = True
                else:  # mqtt option
                    user_input[CONF_PROTOCOL] = "mqtt"
                    user_input[CONF_PORT] = 1883
                    user_input[CONF_VERIFY_SSL] = False  # Not applicable for unencrypted
                del user_input["Port"]
            
            # Test MQTT connection
            result = await self._test_mqtt_connection(user_input)
            
            self.debug_info["broker_setup_end"] = time.time()
            self.debug_info["broker_setup_duration"] = self.debug_info["broker_setup_end"] - self.debug_info["broker_setup_start"]
            _LOGGER.debug("MQTT connection test completed in %.2f seconds", self.debug_info["broker_setup_duration"])
            
            if result["success"]:
                # Save the config
                _LOGGER.debug("MQTT Connection test successful: %s", result.get("details", ""))
                self.mqtt_config.update(user_input)
                # Store debug info for later
                self.mqtt_config["debug_info"] = self._ensure_serializable(self.debug_info)
                return await self.async_step_topics()
            else:
                _LOGGER.error("MQTT Connection test failed: %s", result["message"])
                errors["base"] = result["error_type"]
                # Add detailed error to UI
                if "details" in result:
                    errors["details"] = result["details"]

        # Build the schema using radio buttons for connection options
        schema_dict = {
            vol.Required(CONF_HOST): str,
            vol.Required("Port", default="mqtts"): vol.In({
                "mqtts": "port 8883 (mqtts://)",
                "mqtt": "port 1883 (mqtt://)",
            }),
            vol.Optional(CONF_USERNAME): str,
            vol.Optional(CONF_PASSWORD): str,
            vol.Required(CONF_QOS, default=DEFAULT_QOS): vol.In([0, 1, 2]),
        }
        
        # Add SSL verification option only if port 8883 is selected
        if user_input and user_input.get("Port") == "mqtt":
            # Don't include SSL verification for unencrypted connections
            pass
        else:
            # For encrypted connections, include SSL verification but invert the meaning
            schema_dict[vol.Required("allow_insecure_ssl", default=False)] = bool
        
        data_schema = vol.Schema(schema_dict)

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"debug_info": str(self.debug_info) if self.debug_info else ""},
        )
        
    async def async_step_topics(self, user_input=None):
        """Configure topic structure."""
        errors = {}

        if user_input is not None:
            self.mqtt_config.update(user_input)
            _LOGGER.debug("Topic structure configured: %s", user_input)
            self.debug_info["topic_structure"] = user_input[CONF_TOPIC_STRUCTURE]

            # If custom structure was selected, go to custom topic step
            if user_input[CONF_TOPIC_STRUCTURE] == "custom":
                return await self.async_step_custom_topic()

            # Automatically go to topic discovery
            return await self.async_step_topic_discovery()

        # Build the schema with default MQTT username set to broker username
        data_schema = vol.Schema({
            vol.Required(CONF_TOPIC_PREFIX, default=DEFAULT_TOPIC_PREFIX): str,
            vol.Required(CONF_TOPIC_STRUCTURE, default=DEFAULT_TOPIC_STRUCTURE): vol.In(TOPIC_STRUCTURES),
            vol.Optional(CONF_MQTT_USERNAME, default=self.mqtt_config.get(CONF_USERNAME, "")): str,
        })

        return self.async_show_form(
            step_id="topics",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_custom_topic(self, user_input=None):
        """Configure custom topic structure."""
        errors = {}

        if user_input is not None:
            # Validate the custom structure
            custom_structure = user_input["custom_structure"]

            # Check for required placeholders
            if "{prefix}" not in custom_structure:
                errors["custom_structure"] = "missing_prefix"
            elif "{vehicle_id}" not in custom_structure:
                errors["custom_structure"] = "missing_vehicle_id"
            else:
                # Test for valid format (no invalid placeholders)
                try:
                    test_format = custom_structure.format(
                        prefix="test",
                        vehicle_id="test",
                        mqtt_username="test"
                    )
                    self.mqtt_config[CONF_TOPIC_STRUCTURE] = custom_structure
                    # Go to topic discovery instead of directly to vehicle
                    return await self.async_step_topic_discovery()
                except KeyError as ex:
                    errors["custom_structure"] = "invalid_placeholder"
                    _LOGGER.error("Invalid placeholder in custom structure: %s", ex)
                except ValueError as ex:
                    errors["custom_structure"] = "invalid_format"
                    _LOGGER.error("Invalid format in custom structure: %s", ex)

        # Build the schema
        data_schema = vol.Schema({
            vol.Required("custom_structure"): str,
        })

        return self.async_show_form(
            step_id="custom_topic",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "examples": "{prefix}/{mqtt_username}/{vehicle_id}, {prefix}/client/{vehicle_id}"
            },
        )

    async def async_step_topic_discovery(self, user_input=None):
        """Discover available topics on the broker."""
        # Skip user input handling - we'll automatically discover and proceed
        
        # Discover topics using the broad wildcard
        _LOGGER.debug("Starting topic discovery")
        discovery_result = await self._discover_topics(self.mqtt_config)

        if discovery_result["success"]:
            self.discovered_topics = discovery_result.get("topics", set())
            _LOGGER.debug("Discovered %d topics", len(self.discovered_topics))

            # Extract potential vehicle IDs from discovered topics
            potential_vehicle_ids = self._extract_vehicle_ids(self.discovered_topics, self.mqtt_config)
            self.debug_info["potential_vehicle_ids"] = list(potential_vehicle_ids)
        
        # Proceed to vehicle step regardless of discovery result
        return await self.async_step_vehicle()

    async def async_step_vehicle(self, user_input=None):
        """Configure vehicle settings."""
        errors = {}

        # Suggest vehicle IDs from discovery if available
        suggested_vehicle_ids = self._extract_vehicle_ids(self.discovered_topics, self.mqtt_config)
        default_vehicle_id = next(iter(suggested_vehicle_ids), "")
        
        # If exactly one vehicle ID was found, automatically use it without prompting
        if len(suggested_vehicle_ids) == 1 and default_vehicle_id and not user_input:
            _LOGGER.debug("Only one vehicle ID found: %s. Auto-selecting.", default_vehicle_id)
            user_input = {CONF_VEHICLE_ID: default_vehicle_id}

        if user_input is not None:
            self.mqtt_config.update(user_input)

            _LOGGER.debug("Starting OVMS topic availability test for vehicle: %s", user_input[CONF_VEHICLE_ID])
            self.debug_info["topic_test_start"] = time.time()

            # Format the structure prefix for this vehicle
            structure_prefix = self._format_structure_prefix(self.mqtt_config)
            _LOGGER.debug("Formatted structure prefix: %s", structure_prefix)
            self.debug_info["structure_prefix"] = structure_prefix

            # Test topic availability with the specific vehicle ID
            result = await self._test_topic_availability(self.mqtt_config)

            self.debug_info["topic_test_end"] = time.time()
            self.debug_info["topic_test_duration"] = self.debug_info["topic_test_end"] - self.debug_info["topic_test_start"]
            _LOGGER.debug("Topic availability test completed in %.2f seconds", self.debug_info["topic_test_duration"])

            if result["success"]:
                _LOGGER.debug("Topic availability test successful: %s", result.get("details", ""))

                # Store original vehicle ID for maintaining entity ID consistency
                self.mqtt_config[CONF_ORIGINAL_VEHICLE_ID] = user_input[CONF_VEHICLE_ID]

                # Create a stable unique ID that won't change if vehicle_id changes
                unique_id_base = f"{self.mqtt_config[CONF_HOST]}_{user_input[CONF_VEHICLE_ID]}"
                unique_id = f"ovms_{hashlib.md5(unique_id_base.encode()).hexdigest()}"

                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                # Ensure everything is serializable
                self.mqtt_config["debug_info"] = self._ensure_serializable(self.debug_info)
                
                title = f"OVMS - {self.mqtt_config[CONF_VEHICLE_ID]}"
                return self.async_create_entry(
                    title=title, 
                    data=self.mqtt_config
                )
            else:
                _LOGGER.error("Topic availability test failed: %s", result["message"])
                errors["base"] = result["error_type"]
                # Add detailed error to UI
                if "details" in result:
                    errors["details"] = result["details"]

        # Build the schema
        data_schema = vol.Schema({
            vol.Required(CONF_VEHICLE_ID, default=default_vehicle_id): str,
        })

        return self.async_show_form(
            step_id="vehicle",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "suggested_ids": ", ".join(suggested_vehicle_ids) if suggested_vehicle_ids else "None detected",
                "debug_info": str(self.debug_info) if self.debug_info else "",
            },
        )

    def _extract_vehicle_ids(self, topics, config):
        """Extract potential vehicle IDs from discovered topics."""
        _LOGGER.debug("Extracting potential vehicle IDs from %d topics", len(topics))
        potential_ids = set()
        discovered_username = None

        # Get the topic prefix
        prefix = config.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
        mqtt_username = config.get(CONF_MQTT_USERNAME, "")

        # Try with the configured username first if available
        if mqtt_username:
            pattern = fr"^{re.escape(prefix)}/{re.escape(mqtt_username)}/([^/]+)/"
            _LOGGER.debug("Using pattern to extract vehicle IDs: %s", pattern)

            for topic in topics:
                match = re.match(pattern, topic)
                if match:
                    vehicle_id = match.group(1)
                    # Skip client and rr paths
                    if vehicle_id not in ["client", "rr"]:
                        _LOGGER.debug("Found potential vehicle ID '%s' from topic '%s'", vehicle_id, topic)
                        potential_ids.add(vehicle_id)

        # If no matches found with the username pattern, try a more general pattern
        if not potential_ids:
            general_pattern = fr"^{re.escape(prefix)}/([^/]+)/([^/]+)/"
            _LOGGER.debug("No matches found. Using more general pattern: %s", general_pattern)

            for topic in topics:
                match = re.match(general_pattern, topic)
                if match:
                    username = match.group(1)
                    vehicle_id = match.group(2)
                    if vehicle_id not in ["client", "rr"]:
                        _LOGGER.debug("Found potential vehicle ID '%s' with username '%s' from topic '%s'", 
                                    vehicle_id, username, topic)
                        # Save the discovered username for future use
                        discovered_username = username
                        potential_ids.add(vehicle_id)
            
            # Update the MQTT username in config if discovered
            if discovered_username and discovered_username != mqtt_username:
                _LOGGER.debug("Updating MQTT username from '%s' to discovered '%s'", 
                            mqtt_username, discovered_username)
                config[CONF_MQTT_USERNAME] = discovered_username
                # Also update the mqtt_config in the class
                self.mqtt_config[CONF_MQTT_USERNAME] = discovered_username

        _LOGGER.debug("Extracted %d potential vehicle IDs: %s", len(potential_ids), potential_ids)
        return potential_ids

    def _format_structure_prefix(self, config):
        """Format the topic structure prefix based on the configuration."""
        structure = config.get(CONF_TOPIC_STRUCTURE, DEFAULT_TOPIC_STRUCTURE)
        prefix = config.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
        vehicle_id = config.get(CONF_VEHICLE_ID, "")
        mqtt_username = config.get(CONF_MQTT_USERNAME, "")

        _LOGGER.debug("Formatting structure prefix with: structure=%s, prefix=%s, vehicle_id=%s, mqtt_username=%s", 
                     structure, prefix, vehicle_id, mqtt_username)

        # Replace the variables in the structure
        structure_prefix = structure.format(
            prefix=prefix,
            vehicle_id=vehicle_id,
            mqtt_username=mqtt_username
        )

        _LOGGER.debug("Formatted structure prefix: %s", structure_prefix)
        return structure_prefix

    def _setup_mqtt_client(self, config, client_id=None, log_prefix="MQTT Client"):
        """Set up and configure MQTT client."""
        if not client_id:
            client_id = f"ha_ovms_{uuid.uuid4().hex[:8]}"
            
        protocol = mqtt.MQTTv5 if hasattr(mqtt, 'MQTTv5') else mqtt.MQTTv311
        
        _LOGGER.debug("%s - Creating client with ID: %s", log_prefix, client_id)
        mqttc = mqtt.Client(client_id=client_id, protocol=protocol)
        
        # Configure credentials if provided
        if CONF_USERNAME in config and config[CONF_USERNAME]:
            _LOGGER.debug("%s - Setting username and password", log_prefix)
            mqttc.username_pw_set(
                username=config[CONF_USERNAME],
                password=config[CONF_PASSWORD] if CONF_PASSWORD in config else None,
            )
            
        # Set connection timeout
        mqttc.connect_timeout = 5.0
        
        return mqttc, client_id

    def _create_mqtt_result(self, success, error_type=None, message=None, details=None):
        """Create standardized MQTT result response."""
        result = {"success": success}
        if not success:
            result["error_type"] = error_type or ERROR_UNKNOWN
            result["message"] = message or "Unknown error"
            if details:
                result["details"] = details
        elif details:
            result["details"] = details
        return result

    async def _test_mqtt_connection(self, config):
        """Test if we can connect to the MQTT broker."""
        log_prefix = f"MQTT connection test to {config[CONF_HOST]}:{config[CONF_PORT]}"
        _LOGGER.debug("%s - Starting", log_prefix)
        
        # Initialize debug info for this test
        debug_info = {
            "host": config[CONF_HOST],
            "port": config[CONF_PORT],
            "protocol": config[CONF_PROTOCOL],
            "has_username": bool(config.get(CONF_USERNAME)),
            "test_start_time": time.time(),
        }
        
        # Set up the client
        mqttc, client_id = self._setup_mqtt_client(config, log_prefix=log_prefix)
        debug_info["mqtt_protocol_version"] = "MQTTv5" if hasattr(mqtt, 'MQTTv5') else "MQTTv311"
        
        # Set up connection status for debugging
        connection_status = {"connected": False, "rc": None, "flags": None}
        
        # Define callback for debugging
        def on_connect(client, userdata, flags, rc, properties=None):
            """Handle connection result."""
            connection_status["connected"] = (rc == 0)
            connection_status["rc"] = rc
            connection_status["flags"] = flags
            connection_status["timestamp"] = time.time()
            
            _LOGGER.debug("%s - Connection callback: rc=%s, flags=%s", log_prefix, rc, flags)
            
        def on_disconnect(client, userdata, rc, properties=None):
            """Handle disconnection."""
            connection_status["connected"] = False
            connection_status["disconnect_rc"] = rc
            connection_status["disconnect_timestamp"] = time.time()
            _LOGGER.debug("%s - Disconnected with result code: %s", log_prefix, rc)
            
        def on_log(client, userdata, level, buf):
            """Log MQTT client internal messages."""
            _LOGGER.debug("%s - MQTT Log: %s", log_prefix, buf)
            
        # Configure client callbacks
        if hasattr(mqtt, 'MQTTv5'):
            mqttc.on_connect = on_connect
        else:
            # For MQTT v3.1.1
            def on_connect_v311(client, userdata, flags, rc):
                on_connect(client, userdata, flags, rc, None)
            mqttc.on_connect = on_connect_v311
            
        mqttc.on_disconnect = on_disconnect
        mqttc.on_log = on_log
            
        # Configure TLS if needed
        if config[CONF_PORT] == 8883:
            _LOGGER.debug("%s - Enabling SSL/TLS for port 8883", log_prefix)
            verify_ssl = config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
            try:
                # Use executor to avoid blocking the event loop
                context = await self.hass.async_add_executor_job(ssl.create_default_context)
                # Allow self-signed certificates if insecure is allowed
                if not verify_ssl:
                    _LOGGER.debug("%s - SSL certificate verification disabled (insecure TLS/SSL allowed)", log_prefix)
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                mqttc.tls_set_context(context)
                debug_info["tls_enabled"] = True
                debug_info["tls_verify"] = verify_ssl
            except ssl.SSLError as ssl_err:
                _LOGGER.error("%s - SSL/TLS setup error: %s", log_prefix, ssl_err)
                debug_info["ssl_error"] = str(ssl_err)
                return self._create_mqtt_result(
                    False, 
                    ERROR_TLS_ERROR, 
                    f"SSL/TLS Error: {ssl_err}", 
                    f"SSL configuration failed: {ssl_err}"
                )
        
        debug_info["connect_timeout"] = mqttc.connect_timeout
        
        try:
            # DNS resolution check
            _LOGGER.debug("%s - Resolving hostname", log_prefix)
            dns_start = time.time()
            try:
                socket.gethostbyname(config[CONF_HOST])
                dns_success = True
            except socket.gaierror as err:
                dns_success = False
                dns_error = str(err)
            dns_time = time.time() - dns_start
            
            debug_info["dns_resolution"] = {
                "success": dns_success,
                "time_taken": dns_time,
            }
            
            if not dns_success:
                _LOGGER.error("%s - DNS resolution failed: %s", log_prefix, dns_error)
                debug_info["dns_resolution"]["error"] = dns_error
                return self._create_mqtt_result(
                    False,
                    ERROR_CANNOT_CONNECT,
                    f"DNS resolution failed: {dns_error}",
                    f"Could not resolve hostname '{config[CONF_HOST]}': {dns_error}"
                )
            
            # Port check
            _LOGGER.debug("%s - Checking if port is open", log_prefix)
            port_check_start = time.time()
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            try:
                port_result = s.connect_ex((config[CONF_HOST], config[CONF_PORT]))
                port_open = (port_result == 0)
            except socket.error as err:
                port_open = False
                port_error = str(err)
            finally:
                s.close()
            port_check_time = time.time() - port_check_start
            
            debug_info["port_check"] = {
                "success": port_open,
                "time_taken": port_check_time,
            }
            
            if not port_open:
                _LOGGER.error("%s - Port check failed, port %d is closed", log_prefix, config[CONF_PORT])
                debug_info["port_check"]["error"] = f"Port {config[CONF_PORT]} is closed"
                return self._create_mqtt_result(
                    False,
                    ERROR_CANNOT_CONNECT,
                    f"Port {config[CONF_PORT]} is closed",
                    f"Port {config[CONF_PORT]} on host '{config[CONF_HOST]}' is not open."
                )
            
            # Now try the actual MQTT connection
            _LOGGER.debug("%s - Connecting to broker", log_prefix)
            connect_start = time.time()
            
            # Connect using the executor to avoid blocking
            await self.hass.async_add_executor_job(
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
                if connection_status.get("rc") is not None and connection_status.get("rc") != 0:
                    # Connection failed with specific error code
                    break
                await asyncio.sleep(0.5)
                _LOGGER.debug("%s - Waiting for connection (%d/10)", log_prefix, i+1)
                
            connect_time = time.time() - connect_start
            debug_info["mqtt_connect"] = {
                "success": connected,
                "time_taken": connect_time,
                "status": self._ensure_serializable(connection_status),
            }
            
            mqttc.loop_stop()
            
            if connected:
                _LOGGER.debug("%s - Connection successful", log_prefix)
                # Test subscribing to a topic as a further check
                _LOGGER.debug("%s - Testing topic subscription", log_prefix)
                sub_result = await self._test_subscription(mqttc, config, client_id)
                debug_info["subscription_test"] = self._ensure_serializable(sub_result)
                
                if not sub_result["success"]:
                    try:
                        mqttc.disconnect()
                    except Exception:
                        pass
                    
                    # Prepare detailed error message
                    error_details = sub_result.get("details", "Could not subscribe to test topics")
                    error_topic = sub_result.get("topic", "unknown")
                    
                    return self._create_mqtt_result(
                        False,
                        ERROR_TOPIC_ACCESS_DENIED,
                        f"Topic subscription test failed for {error_topic}",
                        f"Access denied to the test topic '{error_topic}'. This is likely due to MQTT ACL (Access Control List) restrictions. For EMQX broker, ensure the user has 'Subscribe' permission for '{error_topic}' or 'homeassistant/#' wildcard topic. {error_details}"
                    )
                
                try:
                    mqttc.disconnect()
                except Exception:
                    pass
                self.debug_info.update(debug_info)
                return self._create_mqtt_result(
                    True,
                    details="Connection and subscription tests passed successfully"
                )
            else:
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
                        details = "Authentication failed. Please check your username and password."
                    elif rc == 5:
                        error_message = "Connection refused - not authorized"
                        error_type = ERROR_INVALID_AUTH
                        details = "Not authorized to connect. Check your credentials and broker permissions."
                        
                _LOGGER.error("%s - %s (rc=%s)", log_prefix, error_message, rc)
                debug_info["error"] = {
                    "message": error_message,
                    "rc": rc,
                }
                
                self.debug_info.update(debug_info)
                return self._create_mqtt_result(False, error_type, error_message, details)
                
        except socket.timeout:
            _LOGGER.error("%s - Connection timeout", log_prefix)
            debug_info["error"] = {
                "type": "timeout",
                "message": "Connection timeout",
            }
            self.debug_info.update(debug_info)
            return self._create_mqtt_result(
                False,
                ERROR_TIMEOUT,
                "Connection timeout",
                f"Connection to {config[CONF_HOST]}:{config[CONF_PORT]} timed out after {mqttc.connect_timeout} seconds"
            )
        except socket.error as err:
            _LOGGER.error("%s - Connection error: %s", log_prefix, err)
            debug_info["error"] = {
                "type": "socket",
                "message": str(err),
            }
            self.debug_info.update(debug_info)
            return self._create_mqtt_result(
                False,
                ERROR_CANNOT_CONNECT,
                f"Connection error: {err}",
                f"Socket error when connecting to {config[CONF_HOST]}:{config[CONF_PORT]}: {err}"
            )
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.exception("%s - Unexpected error: %s", log_prefix, ex)
            error_type = ERROR_UNKNOWN
            
            if "failed to connect" in str(ex).lower():
                error_type = ERROR_CANNOT_CONNECT
            if "not authorised" in str(ex).lower() or "not authorized" in str(ex).lower():
                error_type = ERROR_INVALID_AUTH
                
            debug_info["error"] = {
                "type": "unexpected",
                "message": str(ex),
            }
            self.debug_info.update(debug_info)
            return self._create_mqtt_result(
                False,
                error_type,
                f"MQTT Error: {ex}",
                f"An unexpected error occurred: {ex}"
            )
            
    async def _test_subscription(self, mqtt_client, config, client_id):
        """Test if we can subscribe to a topic."""
        log_prefix = f"MQTT subscription test for {config[CONF_HOST]}:{config[CONF_PORT]}"
        
        # Use a test topic that should be accessible to all users
        test_topic = f"homeassistant/{client_id}/test"
        qos = config.get(CONF_QOS, DEFAULT_QOS)
        
        subscription_result = {"success": False, "topic": test_topic}
        
        # Define callback for subscription
        def on_subscribe(client, userdata, mid, granted_qos, properties=None):
            """Handle subscription result."""
            _LOGGER.debug("%s - Subscription callback: mid=%s, qos=%s", log_prefix, mid, granted_qos)
            subscription_result["success"] = True
            subscription_result["granted_qos"] = granted_qos
            
        # Configure client callback
        if hasattr(mqtt, 'MQTTv5'):
            mqtt_client.on_subscribe = on_subscribe
        else:
            # For MQTT v3.1.1
            def on_subscribe_v311(client, userdata, mid, granted_qos):
                on_subscribe(client, userdata, mid, granted_qos, None)
            mqtt_client.on_subscribe = on_subscribe_v311
            
        try:
            _LOGGER.debug("%s - Subscribing to test topic: %s", log_prefix, test_topic)
            result = mqtt_client.subscribe(test_topic, qos=qos)
            subscription_result["subscribe_result"] = self._ensure_serializable(result)
            
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
                _LOGGER.debug("%s - Waiting for subscription confirmation (%d/5)", log_prefix, i+1)
                
            if subscription_confirmed:
                _LOGGER.debug("%s - Subscription successful", log_prefix)
                return {"success": True, "topic": test_topic}
            else:
                _LOGGER.error("%s - Subscription not confirmed", log_prefix)
                return {
                    "success": False,
                    "message": "Subscription request was not confirmed by the broker",
                    "topic": test_topic,
                    "details": "The MQTT broker did not confirm the subscription request. This may be due to ACL rules on the broker preventing subscription to the test topic, connectivity issues, or broker configuration. Check the broker's logs and access control settings."
                }
                
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.exception("%s - Subscription error: %s", log_prefix, ex)
            return {
                "success": False,
                "message": f"Subscription error: {ex}",
                "topic": test_topic,
                "details": f"Error while attempting to subscribe to the test topic '{test_topic}'. Check your broker connection and permissions. Full error: {ex}"
            }

    async def _discover_topics(self, config):
        """Discover available OVMS topics on the broker."""
        from .const import DISCOVERY_TOPIC
        import socket
        
        topic_prefix = config.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
        log_prefix = f"Topic discovery for prefix {topic_prefix}"
        _LOGGER.debug("%s - Starting", log_prefix)
        
        # Initialize debug info for this test
        debug_info = {
            "topic_prefix": topic_prefix,
            "test_start_time": time.time(),
        }
        
        # Format the discovery topic
        discovery_topic = DISCOVERY_TOPIC.format(prefix=topic_prefix)
        _LOGGER.debug("%s - Using discovery topic: %s", log_prefix, discovery_topic)
        debug_info["discovery_topic"] = discovery_topic
        
        # Set up the client
        mqttc, client_id = self._setup_mqtt_client(config, log_prefix=log_prefix)
        
        discovered_topics = set()
        connection_status = {"connected": False, "rc": None}
        
        # Define callbacks
        def on_connect(client, userdata, flags, rc, properties=None):
            """Handle connection result."""
            connection_status["connected"] = (rc == 0)
            connection_status["rc"] = rc
            connection_status["timestamp"] = time.time()
            
            _LOGGER.debug("%s - Connection callback: rc=%s, flags=%s", log_prefix, rc, flags)
            
            if rc == 0:
                _LOGGER.debug("%s - Subscribing to discovery topic: %s", log_prefix, discovery_topic)
                client.subscribe(discovery_topic, qos=config.get(CONF_QOS, DEFAULT_QOS))
            
        def on_message(client, userdata, msg):
            """Handle incoming messages."""
            _LOGGER.debug("%s - Message received on topic: %s (payload len: %d)", 
                         log_prefix, msg.topic, len(msg.payload))
            discovered_topics.add(msg.topic)
            
        def on_disconnect(client, userdata, rc, properties=None):
            """Handle disconnection."""
            connection_status["connected"] = False
            connection_status["disconnect_rc"] = rc
            connection_status["disconnect_timestamp"] = time.time()
            _LOGGER.debug("%s - Disconnected with result code: %s", log_prefix, rc)
            
        def on_log(client, userdata, level, buf):
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
            
        # Configure TLS if needed
        if config[CONF_PORT] == 8883:
            verify_ssl = config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
            try:
                # Use executor to avoid blocking the event loop
                context = await self.hass.async_add_executor_job(ssl.create_default_context)
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
                return self._create_mqtt_result(
                    False, 
                    ERROR_TLS_ERROR, 
                    f"SSL/TLS Error: {ssl_err}"
                )
        
        try:
            # Connect to the broker
            _LOGGER.debug("%s - Connecting to broker", log_prefix)
            await self.hass.async_add_executor_job(
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
                return self._create_mqtt_result(
                    False, 
                    ERROR_CANNOT_CONNECT, 
                    f"Failed to connect to MQTT broker (rc={rc})"
                )
                
            # Wait for messages to arrive
            _LOGGER.debug("%s - Waiting for messages", log_prefix)
            await asyncio.sleep(3)  # Wait for up to 3 seconds
                
            # Try to publish a message to stimulate response
            try:
                _LOGGER.debug("%s - Publishing test message to stimulate responses", log_prefix)
                command_id = uuid.uuid4().hex[:8]
                # Use a generic discovery command - this will be ignored if the structure is wrong
                # but might trigger responses from OVMS modules
                test_topic = f"{topic_prefix}/client/rr/command/{command_id}"
                test_payload = "stat"
                
                mqttc.publish(test_topic, test_payload, qos=config.get(CONF_QOS, DEFAULT_QOS))
                _LOGGER.debug("%s - Test message published to %s", log_prefix, test_topic)
                
                # Wait a bit longer for responses
                await asyncio.sleep(2)
            except Exception as ex:
                _LOGGER.warning("%s - Error publishing test message: %s", log_prefix, ex)
            
            # Clean up
            mqttc.loop_stop()
            try:
                mqttc.disconnect()
            except Exception:
                pass
            
            # Return the results
            topics_count = len(discovered_topics)
            
            debug_info["topics_count"] = topics_count
            debug_info["topics"] = list(discovered_topics)
            
            _LOGGER.debug("%s - Discovery complete. Found %d topics", log_prefix, topics_count)
            
            return self._create_mqtt_result(
                True,
                details=f"Discovered {topics_count} topics",
                topics=discovered_topics,
                count=topics_count
            )
            
        except socket.timeout:
            _LOGGER.error("%s - Connection timeout", log_prefix)
            return self._create_mqtt_result(
                False, 
                ERROR_TIMEOUT, 
                "Connection timeout during topic discovery"
            )
        except socket.error as err:
            _LOGGER.error("%s - Connection error: %s", log_prefix, err)
            return self._create_mqtt_result(
                False, 
                ERROR_CANNOT_CONNECT, 
                f"Connection error during topic discovery: {err}"
            )
        except Exception as ex:  # Catch all exceptions
            _LOGGER.error("%s - MQTT error: %s", log_prefix, ex)
            return self._create_mqtt_result(
                False, 
                ERROR_UNKNOWN, 
                f"Error during topic discovery: {ex}"
            )

    async def _test_topic_availability(self, config):
        """Test if the OVMS topics are available for a specific vehicle."""
        from .const import TOPIC_TEMPLATE, COMMAND_TOPIC_TEMPLATE, RESPONSE_TOPIC_TEMPLATE
        import socket
        
        vehicle_id = config[CONF_VEHICLE_ID]
        log_prefix = f"Topic availability test for vehicle {vehicle_id}"
        _LOGGER.debug("%s - Starting", log_prefix)
        
        # Format the structure prefix for this vehicle
        structure_prefix = self._format_structure_prefix(config)
        
        # Initialize debug info for this test
        debug_info = {
            "vehicle_id": vehicle_id,
            "structure_prefix": structure_prefix,
            "test_start_time": time.time(),
        }
        
        # Format the topic template
        topic = TOPIC_TEMPLATE.format(structure_prefix=structure_prefix)
        _LOGGER.debug("%s - Using subscription topic: %s", log_prefix, topic)
        debug_info["subscription_topic"] = topic
        
        # Format command and response topics for request-response test
        command_id = uuid.uuid4().hex[:8]
        command_topic = COMMAND_TOPIC_TEMPLATE.format(structure_prefix=structure_prefix, command_id=command_id)
        response_topic = RESPONSE_TOPIC_TEMPLATE.format(structure_prefix=structure_prefix, command_id=command_id)
        
        _LOGGER.debug("%s - Using command topic: %s", log_prefix, command_topic)
        _LOGGER.debug("%s - Using response topic: %s", log_prefix, response_topic)
        
        debug_info["command_topic"] = command_topic
        debug_info["response_topic"] = response_topic
        
        # Set up the client 
        mqttc, client_id = self._setup_mqtt_client(config, log_prefix=log_prefix)
        
        messages_received = []
        topics_found = set()
        connection_status = {"connected": False, "rc": None}
        responses_received = []
        
        # Define callbacks
        def on_connect(client, userdata, flags, rc, properties=None):
            """Handle connection result."""
            connection_status["connected"] = (rc == 0)
            connection_status["rc"] = rc
            connection_status["timestamp"] = time.time()
            
            _LOGGER.debug("%s - Connection callback: rc=%s, flags=%s", log_prefix, rc, flags)
            
            if rc == 0:
                # Subscribe to general topics and response topic
                _LOGGER.debug("%s - Subscribing to general topic: %s", log_prefix, topic)
                client.subscribe(topic, qos=config.get(CONF_QOS, DEFAULT_QOS))
                
                _LOGGER.debug("%s - Subscribing to response topic: %s", log_prefix, response_topic)
                client.subscribe(response_topic, qos=config.get(CONF_QOS, DEFAULT_QOS))
            
        def on_message(client, userdata, msg):
            """Handle incoming messages."""
            _LOGGER.debug("%s - Message received on topic: %s (payload len: %d)", 
                         log_prefix, msg.topic, len(msg.payload))
            
            message_info = {
                "topic": msg.topic,
                "payload_length": len(msg.payload),
                "timestamp": time.time(),
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
            
        def on_disconnect(client, userdata, rc, properties=None):
            """Handle disconnection."""
            connection_status["connected"] = False
            connection_status["disconnect_rc"] = rc
            connection_status["disconnect_timestamp"] = time.time()
            _LOGGER.debug("%s - Disconnected with result code: %s", log_prefix, rc)
            
        def on_log(client, userdata, level, buf):
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
            
        # Configure TLS if needed
        if config[CONF_PROTOCOL] == "mqtts":
            verify_ssl = config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
            try:
                # Use executor to avoid blocking the event loop
                context = await self.hass.async_add_executor_job(ssl.create_default_context)
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
                self.debug_info.update(debug_info)
                return self._create_mqtt_result(
                    False,
                    ERROR_TLS_ERROR,
                    f"SSL/TLS Error: {ssl_err}",
                    f"SSL configuration failed: {ssl_err}"
                )
            
        # Set up connection timeout
        mqttc.connect_timeout = 5.0
        
        try:
            # Connect to the broker
            _LOGGER.debug("%s - Connecting to broker", log_prefix)
            await self.hass.async_add_executor_job(
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
                self.debug_info.update(debug_info)
                return self._create_mqtt_result(
                    False,
                    ERROR_CANNOT_CONNECT,
                    f"Failed to connect to MQTT broker (rc={rc})",
                    f"Could not connect to broker for topic testing. Result code: {rc}"
                )
                
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
                mqttc.publish(command_topic, "stat", qos=config.get(CONF_QOS, DEFAULT_QOS))
                
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
            except Exception as ex:
                _LOGGER.warning("%s - Error sending command: %s", log_prefix, ex)
                
            # Wait a bit longer for more messages to arrive
            if not messages_received:
                _LOGGER.debug("%s - No messages received, waiting longer", log_prefix)
                await asyncio.sleep(3)
            
            # Clean up
            mqttc.loop_stop()
            try:
                mqttc.disconnect()
            except Exception:
                pass
            
            # Check if we received any messages
            messages_count = len(messages_received)
            topics_count = len(topics_found)
            
            debug_info["messages_received"] = messages_count
            debug_info["topics_found"] = topics_count
            debug_info["topics_list"] = list(topics_found)
            debug_info["messages"] = self._ensure_serializable(messages_received)
            debug_info["responses_received"] = len(responses_received)
            
            _LOGGER.debug("%s - Test complete. Messages: %d, Topics: %d, Responses: %d", 
                         log_prefix, messages_count, topics_count, len(responses_received))
            
            # Even if we didn't receive messages, we'll consider it a success with a warning
            # since MQTT topics might not have data immediately
            if messages_count == 0:
                _LOGGER.warning("%s - No messages received during test", log_prefix)
                
                details = (
                    "No OVMS messages were detected during the test. This could be normal if "
                    "your vehicle is not actively publishing data. The integration will "
                    "continue to monitor for messages."
                )
                
                self.debug_info.update(debug_info)
                return self._create_mqtt_result(
                    True,
                    details=details,
                    message="No messages received, but connection was successful"
                )
            
            self.debug_info.update(debug_info)
            return self._create_mqtt_result(
                True,
                details=f"Found {messages_count} messages on {topics_count} topics"
            )
            
        except socket.timeout:
            _LOGGER.error("%s - Connection timeout", log_prefix)
            debug_info["error"] = {
                "type": "timeout",
                "message": "Connection timeout",
            }
            self.debug_info.update(debug_info)
            return self._create_mqtt_result(
                False,
                ERROR_TIMEOUT,
                "Connection timeout",
                f"Connection to MQTT broker timed out during topic testing"
            )
        except socket.error as err:
            _LOGGER.error("%s - Connection error: %s", log_prefix, err)
            debug_info["error"] = {
                "type": "socket",
                "message": str(err),
            }
            self.debug_info.update(debug_info)
            return self._create_mqtt_result(
                False,
                ERROR_CANNOT_CONNECT,
                f"Connection error: {err}",
                f"Socket error during topic testing: {err}"
            )
        except Exception as ex:  # Catch all exceptions
            _LOGGER.exception("%s - Unexpected error: %s", log_prefix, ex)
            debug_info["error"] = {
                "type": "unexpected",
                "message": str(ex),
            }
            self.debug_info.update(debug_info)
            return self._create_mqtt_result(
                False,
                ERROR_UNKNOWN,
                f"Unexpected error: {ex}",
                f"An unexpected error occurred during topic testing: {ex}"
            )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OVMSOptionsFlow(config_entry)


class OVMSOptionsFlow(config_entries.OptionsFlow):
    """Handle OVMS options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        # Fix: Use a different attribute name to avoid deprecation warning
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = {
            vol.Required(
                CONF_QOS,
                default=self._config_entry.options.get(
                    CONF_QOS, self._config_entry.data.get(CONF_QOS, DEFAULT_QOS)
                ),
            ): vol.In([0, 1, 2]),
            vol.Required(
                CONF_TOPIC_PREFIX,
                default=self._config_entry.options.get(
                    CONF_TOPIC_PREFIX, 
                    self._config_entry.data.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
                ),
            ): str,
            vol.Optional(
                CONF_TOPIC_STRUCTURE,
                default=self._config_entry.options.get(
                    CONF_TOPIC_STRUCTURE,
                    self._config_entry.data.get(CONF_TOPIC_STRUCTURE, DEFAULT_TOPIC_STRUCTURE)
                ),
            ): vol.In(TOPIC_STRUCTURES),
            vol.Required(
                CONF_VERIFY_SSL,
                default=self._config_entry.options.get(
                    CONF_VERIFY_SSL,
                    self._config_entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
                ),
            ): bool,
        }

        return self.async_show_form(step_id="init", data_schema=vol.Schema(options))
