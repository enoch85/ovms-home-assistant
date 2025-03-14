"""Config flow for OVMS integration."""
import asyncio
import hashlib
import logging
import re
import time
import uuid
from typing import Any

import voluptuous as vol  # pylint: disable=import-error

from homeassistant import config_entries  # pylint: disable=import-error
from homeassistant.const import (  # pylint: disable=import-error
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    CONF_PROTOCOL,
)
from homeassistant.core import callback  # pylint: disable=import-error

from ..const import (
    DOMAIN,
    CONFIG_VERSION,
    DEFAULT_QOS,
    DEFAULT_TOPIC_PREFIX,
    DEFAULT_TOPIC_STRUCTURE,
    CONF_VEHICLE_ID,
    CONF_QOS,
    CONF_TOPIC_PREFIX,
    CONF_MQTT_USERNAME,
    CONF_TOPIC_STRUCTURE,
    CONF_VERIFY_SSL,
    CONF_ORIGINAL_VEHICLE_ID,
    TOPIC_STRUCTURES,
    LOGGER_NAME,
)

from .mqtt_connection import test_mqtt_connection
from .topic_discovery import (
    discover_topics,
    test_topic_availability,
    extract_vehicle_ids,
    format_structure_prefix
)
from .options_flow import OVMSOptionsFlow

_LOGGER = logging.getLogger(LOGGER_NAME)


class OVMSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OVMS."""

    VERSION = CONFIG_VERSION
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_PUSH

    def __init__(self):
        """Initialize the OVMS config flow."""
        _LOGGER.debug("Initializing OVMS config flow")
        self.mqtt_config = {}
        self.debug_info = {}
        self.discovered_topics = set()

    def is_matching(self, _user_input):
        """Check if a host + vehicle_id combo is unique."""
        # Implement matching check
        return False

    def _ensure_serializable(self, obj):
        """Convert MQTT objects to serializable types."""
        _LOGGER.debug("Ensuring serializable for type: %s", type(obj).__name__)
        if isinstance(obj, dict):
            return {k: self._ensure_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._ensure_serializable(item) for item in obj]
        elif isinstance(obj, tuple):
            return [self._ensure_serializable(item) for item in obj]
        elif hasattr(obj, '__dict__'):
            _LOGGER.debug(
                "Converting object with __dict__ to serializable: %s",
                type(obj).__name__
            )
            return {
                k: self._ensure_serializable(v)
                for k, v in obj.__dict__.items() if not k.startswith('_')
            }
        elif obj.__class__.__name__ == 'ReasonCodes':
            _LOGGER.debug("Converting ReasonCodes to serializable")
            try:
                return [int(code) for code in obj]
            except (ValueError, TypeError):
                return str(obj)
        else:
            return obj

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            _LOGGER.debug(
                "Starting OVMS MQTT broker setup with input: %s",
                {k: v for k, v in user_input.items() if k != CONF_PASSWORD}
            )
            self.debug_info["broker_setup_start"] = time.time()

            # Extract protocol and port from Port selection
            if "Port" in user_input:
                port_selection = user_input["Port"]
                if port_selection == "8883":
                    user_input[CONF_PROTOCOL] = "mqtts"
                    user_input[CONF_PORT] = 8883
                    user_input[CONF_VERIFY_SSL] = user_input.get("verify_ssl_certificate", True)
                elif port_selection == "8084":
                    user_input[CONF_PROTOCOL] = "wss"
                    user_input[CONF_PORT] = 8084
                    user_input[CONF_VERIFY_SSL] = user_input.get("verify_ssl_certificate", True)
                elif port_selection == "1883":
                    user_input[CONF_PROTOCOL] = "mqtt"
                    user_input[CONF_PORT] = 1883
                    user_input[CONF_VERIFY_SSL] = False
                elif port_selection == "8083":
                    user_input[CONF_PROTOCOL] = "ws"
                    user_input[CONF_PORT] = 8083
                    user_input[CONF_VERIFY_SSL] = False
                del user_input["Port"]

                # Remove the SSL verification option after processing it
                if "verify_ssl_certificate" in user_input:
                    del user_input["verify_ssl_certificate"]

            # Test MQTT connection
            _LOGGER.debug("Testing MQTT connection")
            result = await test_mqtt_connection(self.hass, user_input)

            self.debug_info["broker_setup_end"] = time.time()
            self.debug_info["broker_setup_duration"] = (
                self.debug_info["broker_setup_end"] - self.debug_info["broker_setup_start"]
            )

            _LOGGER.debug(
                "MQTT connection test completed in %.2f seconds: %s",
                self.debug_info["broker_setup_duration"],
                result
            )

            if result["success"]:
                # Save the config
                _LOGGER.debug("MQTT Connection test successful: %s", result.get("details", ""))
                self.mqtt_config.update(user_input)
                # Store debug info for later
                self.mqtt_config["debug_info"] = self._ensure_serializable(self.debug_info)
                return await self.async_step_topics()

            _LOGGER.error("MQTT Connection test failed: %s", result["message"])
            errors["base"] = result["error_type"]
            # Add detailed error to UI
            if "details" in result:
                errors["details"] = result["details"]

        # Build the schema with expanded port options and place SSL verification right after ports
        schema_dict = {
            vol.Required(CONF_HOST): str,
            vol.Required("Port", default="8883"): vol.In({
                "1883": "TCP Port: 1883 (mqtt://)",
                "8083": "WebSocket Port: 8083 (ws://)",
                "8883": "SSL/TLS Port: 8883 (mqtts://)",
                "8084": "Secure WebSocket Port: 8084 (wss://)",
            }),
        }

        # Add SSL verification option right after port selection, but only for secure ports
        if not user_input or user_input.get("Port") in ["8883", "8084", None]:
            schema_dict[vol.Required("verify_ssl_certificate", default=True)] = bool

        # Continue with remaining form fields
        schema_dict.update({
            vol.Optional(CONF_USERNAME): str,
            vol.Optional(CONF_PASSWORD): str,
            vol.Required(CONF_QOS, default=DEFAULT_QOS): vol.In([0, 1, 2]),
        })

        data_schema = vol.Schema(schema_dict)

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "debug_info": str(self.debug_info) if self.debug_info else ""
            },
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
                _LOGGER.debug("Custom topic structure selected, moving to custom_topic step")
                return await self.async_step_custom_topic()

            # Otherwise continue to topic discovery
            _LOGGER.debug("Standard topic structure selected, moving to topic_discovery step")
            return await self.async_step_topic_discovery()

        # Build the schema with default MQTT username set to broker username
        data_schema = vol.Schema({
            vol.Required(CONF_TOPIC_PREFIX, default=DEFAULT_TOPIC_PREFIX): str,
            vol.Required(CONF_TOPIC_STRUCTURE, default=DEFAULT_TOPIC_STRUCTURE): vol.In(
                TOPIC_STRUCTURES
            ),
            vol.Optional(
                CONF_MQTT_USERNAME,
                default=self.mqtt_config.get(CONF_USERNAME, "")
            ): str,
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
            _LOGGER.debug("Validating custom structure: %s", custom_structure)

            # Check for required placeholders
            if "{prefix}" not in custom_structure:
                _LOGGER.error("Missing {prefix} in custom structure")
                errors["custom_structure"] = "missing_prefix"
            elif "{vehicle_id}" not in custom_structure:
                _LOGGER.error("Missing {vehicle_id} in custom structure")
                errors["custom_structure"] = "missing_vehicle_id"
            else:
                # Test for valid format (no invalid placeholders)
                try:
                    test_format = custom_structure.format(
                        prefix="test",
                        vehicle_id="test",
                        mqtt_username="test"
                    )
                    _LOGGER.debug("Custom structure validation successful: %s", test_format)
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
            # Make sure any discovered topics are properly accessed
            _LOGGER.debug("Topic discovery confirmed, moving to vehicle step")
            return await self.async_step_vehicle()

        # Discover topics using the broad wildcard
        _LOGGER.debug("Starting topic discovery")
        discovery_result = await discover_topics(self.hass, self.mqtt_config)

        if discovery_result and discovery_result.get("success", False):
            self.discovered_topics = discovery_result.get("discovered_topics", set())

            topics_count = len(self.discovered_topics or [])
            topics_sample = (list(self.discovered_topics)[:10]
                if topics_count > 10 else self.discovered_topics)

            _LOGGER.debug(
                "Discovered %d topics: %s",
                topics_count,
                topics_sample
            )

            # Extract potential vehicle IDs from discovered topics
            potential_vehicle_ids = extract_vehicle_ids(
                self.discovered_topics,
                self.mqtt_config
            )
            self.debug_info["potential_vehicle_ids"] = list(potential_vehicle_ids)
            _LOGGER.debug("Potential vehicle IDs: %s", potential_vehicle_ids)

            # Create a schema without the confirmation checkbox
            data_schema = vol.Schema({})

            return self.async_show_form(
                step_id="topic_discovery",
                data_schema=data_schema,
                errors=errors,
                description_placeholders={
                    "topic_count": str(len(self.discovered_topics)),
                    "sample_topics": ", ".join(list(self.discovered_topics)[:5]),
                    "potential_vehicle_ids": (
                        ", ".join(potential_vehicle_ids) if potential_vehicle_ids else "None found"
                    ),
                },
            )

        errors["base"] = discovery_result["error_type"]
        _LOGGER.error("Topic discovery failed: %s", discovery_result["message"])

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
        suggested_vehicle_ids = extract_vehicle_ids(
            self.discovered_topics,
            self.mqtt_config
        )
        default_vehicle_id = next(iter(suggested_vehicle_ids), "")
        _LOGGER.debug(
            "Suggested vehicle IDs: %s, default: %s",
            suggested_vehicle_ids,
            default_vehicle_id
        )

        if user_input is not None:
            self.mqtt_config.update(user_input)
            _LOGGER.debug("Vehicle configuration: %s", user_input)

            _LOGGER.debug(
                "Starting OVMS topic availability test for vehicle: %s",
                user_input[CONF_VEHICLE_ID]
            )
            self.debug_info["topic_test_start"] = time.time()

            # Format the structure prefix for this vehicle
            structure_prefix = format_structure_prefix(self.mqtt_config)
            _LOGGER.debug("Formatted structure prefix: %s", structure_prefix)
            self.debug_info["structure_prefix"] = structure_prefix

            # Test topic availability with the specific vehicle ID
            result = await test_topic_availability(self.hass, self.mqtt_config)

            self.debug_info["topic_test_end"] = time.time()
            self.debug_info["topic_test_duration"] = (
                self.debug_info["topic_test_end"] - self.debug_info["topic_test_start"]
            )

            _LOGGER.debug(
                "Topic availability test completed in %.2f seconds: %s",
                self.debug_info["topic_test_duration"],
                result
            )

            if result["success"]:
                _LOGGER.debug("Topic availability test successful: %s", result.get("details", ""))

                # Store original vehicle ID for maintaining entity ID consistency
                self.mqtt_config[CONF_ORIGINAL_VEHICLE_ID] = user_input[CONF_VEHICLE_ID]

                # Create a stable unique ID that won't change if vehicle_id changes
                unique_id_base = f"{self.mqtt_config[CONF_HOST]}_{user_input[CONF_VEHICLE_ID]}"
                unique_id = f"ovms_{hashlib.md5(unique_id_base.encode()).hexdigest()}"
                _LOGGER.debug("Generated unique ID for config entry: %s", unique_id)

                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                # Ensure everything is serializable
                self.mqtt_config["debug_info"] = self._ensure_serializable(self.debug_info)

                # Log complete final configuration
                _LOGGER.debug(
                    "Final config for entry creation: %s",
                    {k: v for k, v in self.mqtt_config.items() if k != CONF_PASSWORD}
                )

                title = f"OVMS - {self.mqtt_config[CONF_VEHICLE_ID]}"
                _LOGGER.info("Creating config entry with title: %s", title)
                return self.async_create_entry(
                    title=title,
                    data=self.mqtt_config
                )

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
                "suggested_ids": (
                    ", ".join(suggested_vehicle_ids) if suggested_vehicle_ids else "None detected"
                ),
                "debug_info": str(self.debug_info) if self.debug_info else "",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OVMSOptionsFlow(config_entry)
