"""Config flow for OVMS integration."""
import asyncio
import logging
import re
import time
import uuid
import hashlib
from typing import Any, Dict, Optional, Set

import voluptuous as vol

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
from .helpers.mqtt_helper import (
    test_mqtt_broker,
    ensure_serializable,
)
from .helpers.error_handler import OVMSError

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
            result = await test_mqtt_broker(self.hass, user_input)
            
            self.debug_info["broker_setup_end"] = time.time()
            self.debug_info["broker_setup_duration"] = self.debug_info["broker_setup_end"] - self.debug_info["broker_setup_start"]
            _LOGGER.debug("MQTT connection test completed in %.2f seconds", self.debug_info["broker_setup_duration"])
            
            if result["success"]:
                # Save the config
                _LOGGER.debug("MQTT Connection test successful: %s", result.get("details", ""))
                self.mqtt_config.update(user_input)
                # Store debug info for later
                self.mqtt_config["debug_info"] = ensure_serializable(self.debug_info)
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

            # Otherwise continue to topic discovery
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
        errors = {}

        if user_input is not None:
            self.mqtt_config.update(user_input)
            return await self.async_step_vehicle()

        # Discover topics using the broad wildcard
        _LOGGER.debug("Starting topic discovery")
        discovery_result = await self._discover_topics(self.mqtt_config)

        if discovery_result["success"]:
            self.discovered_topics = discovery_result.get("topics", set())
            _LOGGER.debug("Discovered %d topics", len(self.discovered_topics))

            # Extract potential vehicle IDs from discovered topics
            potential_vehicle_ids = self._extract_vehicle_ids(self.discovered_topics, self.mqtt_config)
            self.debug_info["potential_vehicle_ids"] = list(potential_vehicle_ids)

            # Create a schema with the discovered info
            data_schema = vol.Schema({
                vol.Required("confirm_discovery", default=True): bool,
            })

            return self.async_show_form(
                step_id="topic_discovery",
                data_schema=data_schema,
                errors=errors,
                description_placeholders={
                    "topic_count": str(len(self.discovered_topics)),
                    "sample_topics": ", ".join(list(self.discovered_topics)[:5]),
                    "potential_vehicle_ids": ", ".join(potential_vehicle_ids) if potential_vehicle_ids else "None found",
                },
            )
        else:
            errors["base"] = discovery_result["error_type"]
            # Create an empty schema to show error
            data_schema = vol.Schema({
                vol.Required("retry_discovery", default=True): bool,
            })

            return self.async_show_form(
                step_id="topic_discovery",
                data_schema=data_schema,
                errors=errors,
                description_placeholders={
                    "error_message": discovery_result["message"],
                },
            )

    async def async_step_vehicle(self, user_input=None):
        """Configure vehicle settings."""
        errors = {}

        # Suggest vehicle IDs from discovery if available
        suggested_vehicle_ids = self._extract_vehicle_ids(self.discovered_topics, self.mqtt_config)
        default_vehicle_id = next(iter(suggested_vehicle_ids), "")

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
                self.mqtt_config["debug_info"] = ensure_serializable(self.debug_info)
                
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

    def _extract_vehicle_ids(self, topics: Set[str], config: Dict[str, Any]) -> Set[str]:
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

    def _format_structure_prefix(self, config: Dict[str, Any]) -> str:
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

    async def _discover_topics(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Discover available OVMS topics on the broker."""
        # Import MQTT client code here to avoid circular imports
        from .mqtt import OVMSMQTTClient
        
        # Create a temporary MQTT client to discover topics
        topic_prefix = config.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
        discovery_prefix = DISCOVERY_TOPIC.format(prefix=topic_prefix)
        
        # Create a temporary MQTT client
        temp_client = OVMSMQTTClient(self.hass, config)
        
        # Set up the client
        if not await temp_client.async_setup():
            return {
                "success": False,
                "error_type": ERROR_CANNOT_CONNECT,
                "message": "Failed to set up MQTT client for topic discovery"
            }
            
        # Wait for some time to collect topics
        discovered_topics = set()
        try:
            for _ in range(3):  # Try for 3 seconds
                await asyncio.sleep(1)
                # Get discovered topics
                discovered_topics.update(temp_client.discovered_topics)
                
            # Shut down the client
            await temp_client.async_shutdown()
            
            if not discovered_topics:
                return {
                    "success": False,
                    "error_type": ERROR_NO_TOPICS,
                    "message": "No topics discovered"
                }
                
            return {
                "success": True,
                "topics": discovered_topics,
                "count": len(discovered_topics)
            }
            
        except Exception as ex:
            # Ensure client is shut down
            try:
                await temp_client.async_shutdown()
            except Exception:
                pass
                
            # Return error
            return {
                "success": False,
                "error_type": ERROR_UNKNOWN,
                "message": f"Error during topic discovery: {ex}"
            }

    async def _test_topic_availability(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Test if the OVMS topics are available for a specific vehicle."""
        # Import MQTT client code here to avoid circular imports
        from .mqtt import OVMSMQTTClient
        
        # Format the structure prefix with the vehicle ID
        structure_prefix = self._format_structure_prefix(config)
        
        # Create a temporary MQTT client to test topics
        temp_client = OVMSMQTTClient(self.hass, config)
        temp_client.structure_prefix = structure_prefix
        
        # Set up the client
        if not await temp_client.async_setup():
            return {
                "success": False,
                "error_type": ERROR_CANNOT_CONNECT,
                "message": "Failed to set up MQTT client for topic testing"
            }
            
        # Wait for some time to collect messages
        messages_received = []
        try:
            for _ in range(5):  # Try for 5 seconds
                await asyncio.sleep(1)
                # Get received messages
                messages_received = list(temp_client.topic_cache.keys())
                if messages_received:
                    break
                    
            # Try to send a command to stimulate responses
            command_id = uuid.uuid4().hex[:8]
            test_result = await temp_client.async_send_command("stat", "", command_id, timeout=3)
            
            # Wait a bit more for responses
            await asyncio.sleep(2)
            
            # Update messages received
            messages_received = list(temp_client.topic_cache.keys())
            
            # Shut down the client
            await temp_client.async_shutdown()
            
            # Even if we didn't receive messages, consider it a success with a warning
            if not messages_received:
                _LOGGER.warning("No messages received during topic test for vehicle %s", config[CONF_VEHICLE_ID])
                
                return {
                    "success": True,
                    "message": "No messages received, but connection was successful",
                    "details": (
                        "No OVMS messages were detected during the test. This could be normal if "
                        "your vehicle is not actively publishing data. The integration will "
                        "continue to monitor for messages."
                    ),
                }
                
            return {
                "success": True,
                "details": f"Found {len(messages_received)} messages",
                "message_count": len(messages_received)
            }
            
        except Exception as ex:
            # Ensure client is shut down
            try:
                await temp_client.async_shutdown()
            except Exception:
                pass
                
            # Return error
            return {
                "success": False,
                "error_type": ERROR_UNKNOWN,
                "message": f"Error during topic testing: {ex}"
            }

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OVMSOptionsFlow(config_entry)


class OVMSOptionsFlow(config_entries.OptionsFlow):
    """Handle OVMS options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
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
