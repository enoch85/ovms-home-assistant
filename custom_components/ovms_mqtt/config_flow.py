"""Config flow for OVMS MQTT integration."""
from __future__ import annotations

from typing import Any, Dict, Optional
import asyncio
import logging
import socket
import ssl

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_TOPIC_PREFIX,
    DEFAULT_TOPIC_PREFIX,
    CONF_VEHICLE_ID,
    DEFAULT_VEHICLE_ID,
    CONF_QOS,
    DEFAULT_QOS,
    CONF_CONNECTION_TYPE,
    CONNECTION_TYPE_STANDARD,
    CONNECTION_TYPE_SECURE,
    CONNECTION_TYPE_WEBSOCKETS,
    CONNECTION_TYPE_WEBSOCKETS_SECURE,
    CONNECTION_TYPES,
    DEFAULT_PORT,
    DEFAULT_PORT_SSL,
    DEFAULT_PORT_WS,
    DEFAULT_PORT_WSS,
    QOS_OPTIONS,
)

_LOGGER = logging.getLogger(__name__)


async def validate_mqtt_connection(
    hass: HomeAssistant,
    host: str,
    port: int,
    username: Optional[str] = None,
    password: Optional[str] = None,
    ssl_enabled: bool = False,
) -> Optional[str]:
    """Test if we can connect to the MQTT broker."""
    import paho.mqtt.client as mqtt

    result = None

    def _on_connect(client, userdata, flags, result_code, properties=None):
        """Handle connection result."""
        nonlocal result
        result = result_code

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.on_connect = _on_connect

        if username and password:
            client.username_pw_set(username, password)

        if ssl_enabled:
            client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
            client.tls_insecure_set(False)

        # Log connection attempt
        _LOGGER.debug("Testing connection to %s:%s (SSL: %s)", host, port, ssl_enabled)

        await hass.async_add_executor_job(client.connect, host, port, 5)
        await hass.async_add_executor_job(client.loop_start)

        # Wait for connection result
        for _ in range(10):
            if result is not None:
                break
            await asyncio.sleep(0.5)

        await hass.async_add_executor_job(client.loop_stop)

        # Check connection result
        if result is not None and result != 0:
            _LOGGER.error("Failed to connect to MQTT broker: %s", result)
            # Map result codes to error messages
            if result == 1:
                return "invalid_protocol"
            if result == 2:
                return "invalid_client_id"
            if result == 3:
                return "broker_unavailable"
            if result == 4:
                return "invalid_auth"
            if result == 5:
                return "not_authorized"
            return "cannot_connect"
        if result is None:
            _LOGGER.error("Connection timeout to MQTT broker")
            return "timeout_connect"

    except socket.gaierror:
        _LOGGER.error("Could not resolve hostname: %s", host)
        return "invalid_host"
    except OSError as exc:
        _LOGGER.error("Failed to connect to MQTT broker: %s", exc)
        return "cannot_connect"
    except Exception as exc:  # pylint: disable=broad-except
        _LOGGER.exception("Unexpected error: %s", exc)
        return "unknown"
    finally:
        # Clean up
        try:
            client.disconnect()
        except Exception:  # pylint: disable=broad-except
            pass

    return None


class OVMSMQTTConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OVMS MQTT."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._user_input: Dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return OVMSMQTTOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            return await self.async_step_broker()

        return self.async_show_form(step_id="user")

    async def async_step_broker(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Configure the broker connection."""
        errors = {}

        if user_input is not None:
            # Get values from user input
            host = user_input[CONF_HOST]
            conn_type = user_input.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_STANDARD)
            username = user_input.get(CONF_USERNAME)
            password = user_input.get(CONF_PASSWORD)

            # Determine port and SSL based on connection type
            ssl_enabled = conn_type in (
                CONNECTION_TYPE_SECURE, CONNECTION_TYPE_WEBSOCKETS_SECURE
            )
            if conn_type == CONNECTION_TYPE_STANDARD:
                port = DEFAULT_PORT
            elif conn_type == CONNECTION_TYPE_SECURE:
                port = DEFAULT_PORT_SSL
            elif conn_type == CONNECTION_TYPE_WEBSOCKETS:
                port = DEFAULT_PORT_WS
            else:  # Secure WebSockets
                port = DEFAULT_PORT_WSS

            # Override with manual port if provided
            if CONF_PORT in user_input and user_input[CONF_PORT]:
                port = user_input[CONF_PORT]

            # Test connection
            error = await validate_mqtt_connection(
                self.hass, host, port, username, password, ssl_enabled
            )

            if not error:
                # Save connection settings
                self._user_input.update({
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_SSL: ssl_enabled,
                    CONF_USERNAME: username,
                    CONF_PASSWORD: password,
                    CONF_CONNECTION_TYPE: conn_type,
                })
                # Proceed to OVMS settings
                return await self.async_step_ovms()

            errors["base"] = error

        # Prepare schema
        data_schema = vol.Schema({
            vol.Required(CONF_HOST, default="localhost"): str,
            vol.Required(
                CONF_CONNECTION_TYPE, default=CONNECTION_TYPE_STANDARD
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": t, "label": CONNECTION_TYPES[t]}
                        for t in CONNECTION_TYPES
                    ],
                    translation_key="connection_type",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(CONF_PORT): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=65535,
                    mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(CONF_USERNAME): str,
            vol.Optional(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        })

        return self.async_show_form(
            step_id="broker",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_ovms(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Configure OVMS specific settings."""
        errors = {}

        if user_input is not None:
            # Get values from user input
            topic_prefix = user_input.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
            vehicle_id = user_input.get(CONF_VEHICLE_ID, DEFAULT_VEHICLE_ID)
            qos = user_input.get(CONF_QOS, DEFAULT_QOS)

            # Update user input
            self._user_input.update({
                CONF_TOPIC_PREFIX: topic_prefix,
                CONF_VEHICLE_ID: vehicle_id,
                CONF_QOS: qos,
            })

            # Check for existing entries
            host = self._user_input.get(CONF_HOST)
            await self.async_set_unique_id(f"{DOMAIN}_{host}_{vehicle_id}")
            self._abort_if_unique_id_configured()

            # Create config entry
            return self.async_create_entry(
                title=f"OVMS {vehicle_id} on {host}",
                data=self._user_input,
            )

        # Prepare schema with QoS dropdown instead of slider
        data_schema = vol.Schema({
            vol.Required(CONF_TOPIC_PREFIX, default=DEFAULT_TOPIC_PREFIX): str,
            vol.Required(CONF_VEHICLE_ID, default=DEFAULT_VEHICLE_ID): str,
            vol.Required(CONF_QOS, default=DEFAULT_QOS): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": qos_level, "label": QOS_OPTIONS[qos_level]}
                        for qos_level in QOS_OPTIONS
                    ],
                    translation_key="qos_level",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        })

        return self.async_show_form(
            step_id="ovms",
            data_schema=data_schema,
            errors=errors,
        )


class OVMSMQTTOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for OVMS MQTT integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self.current_config = dict(config_entry.data)
        # Add options to current_config
        if config_entry.options:
            self.current_config.update(config_entry.options)

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            if user_input.get("edit_connection", False):
                return await self.async_step_broker()
            if user_input.get("edit_ovms", False):
                return await self.async_step_ovms()
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("edit_connection", default=False): selector.BooleanSelector(),
                vol.Required("edit_ovms", default=True): selector.BooleanSelector(),
            }),
        )

    async def async_step_broker(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle broker options."""
        errors = {}

        if user_input is not None:
            # Get values from user input
            host = user_input[CONF_HOST]
            conn_type = user_input.get(CONF_CONNECTION_TYPE)
            username = user_input.get(CONF_USERNAME)
            password = user_input.get(CONF_PASSWORD)
            
            # If password is empty, keep the existing one
            if not password and self.current_config.get(CONF_PASSWORD):
                password = self.current_config[CONF_PASSWORD]

            # Determine port and SSL based on connection type
            ssl_enabled = conn_type in (
                CONNECTION_TYPE_SECURE, CONNECTION_TYPE_WEBSOCKETS_SECURE
            )
            if conn_type == CONNECTION_TYPE_STANDARD:
                port = DEFAULT_PORT
            elif conn_type == CONNECTION_TYPE_SECURE:
                port = DEFAULT_PORT_SSL
            elif conn_type == CONNECTION_TYPE_WEBSOCKETS:
                port = DEFAULT_PORT_WS
            else:  # Secure WebSockets
                port = DEFAULT_PORT_WSS

            # Override with manual port if provided
            if CONF_PORT in user_input and user_input[CONF_PORT]:
                port = user_input[CONF_PORT]

            # Test connection
            error = await validate_mqtt_connection(
                self.hass, host, port, username, password, ssl_enabled
            )

            if not error:
                # Update configuration
                updated_config = {
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_SSL: ssl_enabled,
                    CONF_USERNAME: username,
                    CONF_PASSWORD: password,
                    CONF_CONNECTION_TYPE: conn_type,
                }

                # Check if we should also edit OVMS settings
                if user_input.get("edit_ovms", False):
                    self.current_config.update(updated_config)
                    return await self.async_step_ovms()
                
                # Update existing entry data
                existing_data = dict(self.current_config)
                existing_data.update(updated_config)
                
                return self.async_create_entry(title="", data=existing_data)

            errors["base"] = error

        # Get current connection type
        conn_type = self.get_current_connection_type()
        
        # Prepare schema
        data_schema = vol.Schema({
            vol.Required(
                CONF_HOST, 
                default=self.current_config.get(CONF_HOST)
            ): str,
            vol.Required(
                CONF_CONNECTION_TYPE, 
                default=conn_type
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": t, "label": CONNECTION_TYPES[t]}
                        for t in CONNECTION_TYPES
                    ],
                    translation_key="connection_type",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(CONF_PORT): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=65535,
                    mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                CONF_USERNAME,
                description={"suggested_value": self.current_config.get(CONF_USERNAME)}
            ): str,
            vol.Optional(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required("edit_ovms", default=False): selector.BooleanSelector(),
        })

        return self.async_show_form(
            step_id="broker",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "username_notice": (
                    f"Current username: {self.current_config.get(CONF_USERNAME)}"
                    if self.current_config.get(CONF_USERNAME)
                    else "No username set"
                ),
                "password_notice": (
                    "Password is set"
                    if self.current_config.get(CONF_PASSWORD)
                    else "No password set"
                ),
            },
        )

    def get_current_connection_type(self) -> str:
        """Determine the current connection type from settings."""
        port = self.current_config.get(CONF_PORT, DEFAULT_PORT)
        ssl_enabled = self.current_config.get(CONF_SSL, False)
        
        # If connection_type is already set, use it
        if CONF_CONNECTION_TYPE in self.current_config:
            return self.current_config[CONF_CONNECTION_TYPE]
        
        # Otherwise, determine from port and SSL
        if ssl_enabled and port == DEFAULT_PORT_SSL:
            return CONNECTION_TYPE_SECURE
        if ssl_enabled and port == DEFAULT_PORT_WSS:
            return CONNECTION_TYPE_WEBSOCKETS_SECURE
        if not ssl_enabled and port == DEFAULT_PORT_WS:
            return CONNECTION_TYPE_WEBSOCKETS
        return CONNECTION_TYPE_STANDARD

    async def async_step_ovms(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle OVMS specific options."""
        if user_input is not None:
            # Update options
            updated_config = {
                CONF_TOPIC_PREFIX: user_input.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX),
                CONF_VEHICLE_ID: user_input.get(CONF_VEHICLE_ID, DEFAULT_VEHICLE_ID),
                CONF_QOS: user_input.get(CONF_QOS, DEFAULT_QOS),
            }
            
            # Update existing entry data
            existing_data = dict(self.current_config)
            existing_data.update(updated_config)
            
            return self.async_create_entry(title="", data=existing_data)

        # Prepare schema with QoS dropdown instead of slider
        data_schema = vol.Schema({
            vol.Required(
                CONF_TOPIC_PREFIX,
                default=self.current_config.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
            ): str,
            vol.Required(
                CONF_VEHICLE_ID,
                default=self.current_config.get(CONF_VEHICLE_ID, DEFAULT_VEHICLE_ID)
            ): str,
            vol.Required(
                CONF_QOS,
                default=self.current_config.get(CONF_QOS, DEFAULT_QOS)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        {"value": qos_level, "label": QOS_OPTIONS[qos_level]}
                        for qos_level in QOS_OPTIONS
                    ],
                    translation_key="qos_level",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        })

        return self.async_show_form(
            step_id="ovms",
            data_schema=data_schema,
        )
