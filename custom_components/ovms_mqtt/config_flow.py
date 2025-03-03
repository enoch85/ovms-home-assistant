"""Config flow for OVMS MQTT integration."""
from __future__ import annotations

from typing import Any, Dict, Optional
import asyncio
import logging
import socket
import ssl
import os.path

import voluptuous as vol
# Import paho.mqtt at the module level to avoid blocking in event loop
import paho.mqtt.client as mqtt

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
from homeassistant.helpers import selector, config_validation as cv

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
    CONF_TLS_INSECURE,
    DEFAULT_TLS_INSECURE,
    CONF_CERTIFICATE_PATH,
    CONF_AVAILABILITY_TIMEOUT,
    DEFAULT_AVAILABILITY_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


def is_valid_certificate_path(path: str) -> bool:
    """Validate that the certificate file exists."""
    return os.path.isfile(path) if path else True


async def validate_mqtt_connection(
    hass: HomeAssistant,
    host: str,
    port: int,
    username: Optional[str] = None,
    password: Optional[str] = None,
    ssl_enabled: bool = False,
    tls_insecure: bool = DEFAULT_TLS_INSECURE,
    certificate_path: Optional[str] = None,
) -> Optional[str]:
    """Test if we can connect to the MQTT broker."""
    result = None
    client = None

    def _on_connect(client, userdata, flags, result_code, properties=None):
        """Handle connection result."""
        nonlocal result
        result = result_code

    def _setup_client():
        """Set up the MQTT client."""
        nonlocal client
        # Support both old and new versions of paho-mqtt
        try:
            # For paho-mqtt >= 2.0.0
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            client.on_connect = _on_connect
        except (AttributeError, TypeError):
            # Fallback for paho-mqtt < 2.0.0
            client = mqtt.Client()
            # Adjust the callback parameter format for older versions
            client.on_connect = lambda client, userdata, flags, rc: _on_connect(client, userdata, flags, rc)

        if username and password:
            client.username_pw_set(username, password)

        if ssl_enabled:
            # Create SSL context with certificate verification options
            if tls_insecure:
                client.tls_set(
                    ca_certs=certificate_path if certificate_path else None,
                    cert_reqs=ssl.CERT_NONE
                )
                client.tls_insecure_set(True)
            else:
                client.tls_set(
                    ca_certs=certificate_path if certificate_path else None,
                    cert_reqs=ssl.CERT_REQUIRED
                )
                client.tls_insecure_set(False)

        # Log connection attempt
        _LOGGER.debug(
            "Testing connection to %s:%s (SSL: %s, Verify: %s)",
            host, port, ssl_enabled, not tls_insecure
        )

    def _connect_mqtt():
        """Connect to MQTT broker."""
        nonlocal client
        client.connect(host, port, 5)
        client.loop_start()

    def _disconnect_mqtt():
        """Disconnect from MQTT broker."""
        nonlocal client
        if client:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:  # pylint: disable=broad-except
                pass

    try:
        # Setup client in executor to avoid blocking event loop
        await hass.async_add_executor_job(_setup_client)
        
        # Connect in executor
        await hass.async_add_executor_job(_connect_mqtt)

        # Wait for connection result
        for _ in range(10):
            if result is not None:
                break
            await asyncio.sleep(0.5)

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
        # Clean up - must run even if exceptions occur
        await hass.async_add_executor_job(_disconnect_mqtt)

    return None


def _deep_update(target: Dict, source: Dict) -> Dict:
    """Update a nested dictionary with another nested dictionary."""
    for key, value in source.items():
        if isinstance(value, Dict) and key in target and isinstance(target[key], Dict):
            target[key] = _deep_update(target[key], value)
        else:
            target[key] = value
    return target


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
            tls_insecure = user_input.get(CONF_TLS_INSECURE, DEFAULT_TLS_INSECURE)
            certificate_path = user_input.get(CONF_CERTIFICATE_PATH)

            # Validate certificate path if provided
            if certificate_path and not is_valid_certificate_path(certificate_path):
                errors["certificate_path"] = "invalid_certificate"
            else:
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

                # Validate QoS if provided
                qos = user_input.get(CONF_QOS)
                if qos is not None and qos not in QOS_OPTIONS:
                    errors[CONF_QOS] = "invalid_qos"

                if not errors:
                    # Test connection
                    error = await validate_mqtt_connection(
                        self.hass, host, port, username, password, ssl_enabled,
                        tls_insecure, certificate_path
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
                            CONF_TLS_INSECURE: tls_insecure,
                        })
                        
                        # Add certificate path if provided
                        if certificate_path:
                            self._user_input[CONF_CERTIFICATE_PATH] = certificate_path
                            
                        # Proceed to OVMS settings
                        return await self.async_step_ovms()

                    errors["base"] = error

        # Prepare schema for broker configuration
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
        
        # Add SSL/TLS options if a secure connection type is selected
        if user_input and user_input.get(CONF_CONNECTION_TYPE) in [
            CONNECTION_TYPE_SECURE, CONNECTION_TYPE_WEBSOCKETS_SECURE
        ]:
            advanced_options = {
                vol.Optional(
                    CONF_TLS_INSECURE, default=DEFAULT_TLS_INSECURE
                ): bool,
                vol.Optional(CONF_CERTIFICATE_PATH): str,
            }
            data_schema = data_schema.extend(advanced_options)

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
            availability_timeout = user_input.get(
                CONF_AVAILABILITY_TIMEOUT, DEFAULT_AVAILABILITY_TIMEOUT
            )

            # Validate QoS value
            if not isinstance(qos, int) or qos not in QOS_OPTIONS:
                errors[CONF_QOS] = "invalid_qos"
            elif not errors:
                # Update user input
                self._user_input.update({
                    CONF_TOPIC_PREFIX: topic_prefix,
                    CONF_VEHICLE_ID: vehicle_id,
                    CONF_QOS: qos,
                    CONF_AVAILABILITY_TIMEOUT: availability_timeout,
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
                        for qos_level in sorted(QOS_OPTIONS.keys())
                    ],
                    translation_key="qos_level",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_AVAILABILITY_TIMEOUT, default=DEFAULT_AVAILABILITY_TIMEOUT
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=3600,
                    step=30,
                    unit_of_measurement="seconds",
                    mode=selector.NumberSelectorMode.BOX,
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
            self.current_config = _deep_update(
                self.current_config, dict(config_entry.options)
            )

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
            tls_insecure = user_input.get(CONF_TLS_INSECURE, DEFAULT_TLS_INSECURE)
            certificate_path = user_input.get(CONF_CERTIFICATE_PATH)
            
            # If password is empty, keep the existing one
            if not password and self.current_config.get(CONF_PASSWORD):
                password = self.current_config[CONF_PASSWORD]

            # Validate certificate path if provided
            if certificate_path and not is_valid_certificate_path(certificate_path):
                errors["certificate_path"] = "invalid_certificate"
            else:
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

                # Validate QoS if provided
                qos = user_input.get(CONF_QOS)
                if qos is not None and qos not in QOS_OPTIONS:
                    errors[CONF_QOS] = "invalid_qos"

                if not errors:
                    # Test connection
                    error = await validate_mqtt_connection(
                        self.hass, host, port, username, password, ssl_enabled,
                        tls_insecure, certificate_path
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
                            CONF_TLS_INSECURE: tls_insecure,
                        }
                        
                        # Add certificate path if provided
                        if certificate_path:
                            updated_config[CONF_CERTIFICATE_PATH] = certificate_path

                        # Check if we should also edit OVMS settings
                        if user_input.get("edit_ovms", False):
                            self.current_config = _deep_update(
                                self.current_config, updated_config
                            )
                            return await self.async_step_ovms()
                        
                        # Update existing entry data with deep merge
                        existing_data = dict(self.current_config)
                        updated_data = _deep_update(existing_data, updated_config)
                        
                        return self.async_create_entry(title="", data=updated_data)

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
        
        # Add SSL/TLS options if a secure connection type is selected
        is_secure = conn_type in [
            CONNECTION_TYPE_SECURE, CONNECTION_TYPE_WEBSOCKETS_SECURE
        ]
        
        if is_secure:
            ssl_options = {
                vol.Optional(
                    CONF_TLS_INSECURE, 
                    default=self.current_config.get(
                        CONF_TLS_INSECURE, DEFAULT_TLS_INSECURE
                    )
                ): bool,
                vol.Optional(
                    CONF_CERTIFICATE_PATH,
                    description={
                        "suggested_value": self.current_config.get(CONF_CERTIFICATE_PATH)
                    }
                ): str,
            }
            data_schema = data_schema.extend(ssl_options)

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
        # If connection_type is already set, use it
        if CONF_CONNECTION_TYPE in self.current_config:
            return self.current_config[CONF_CONNECTION_TYPE]
        
        # Otherwise, determine from port and SSL
        port = self.current_config.get(CONF_PORT, DEFAULT_PORT)
        ssl_enabled = self.current_config.get(CONF_SSL, False)
        
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
        errors = {}

        if user_input is not None:
            # Validate QoS
            qos = user_input.get(CONF_QOS)
            if qos is not None and qos not in QOS_OPTIONS:
                errors[CONF_QOS] = "invalid_qos"
            elif not errors:
                # Update options
                updated_config = {
                    CONF_TOPIC_PREFIX: user_input.get(
                        CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX
                    ),
                    CONF_VEHICLE_ID: user_input.get(
                        CONF_VEHICLE_ID, DEFAULT_VEHICLE_ID
                    ),
                    CONF_QOS: user_input.get(CONF_QOS, DEFAULT_QOS),
                    CONF_AVAILABILITY_TIMEOUT: user_input.get(
                        CONF_AVAILABILITY_TIMEOUT, DEFAULT_AVAILABILITY_TIMEOUT
                    ),
                }
                
                # Update existing entry data with deep merge
                existing_data = dict(self.current_config)
                updated_data = _deep_update(existing_data, updated_config)
                
                return self.async_create_entry(title="", data=updated_data)

        # Prepare schema with QoS dropdown
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
                        for qos_level in sorted(QOS_OPTIONS.keys())
                    ],
                    translation_key="qos_level",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_AVAILABILITY_TIMEOUT,
                default=self.current_config.get(
                    CONF_AVAILABILITY_TIMEOUT, DEFAULT_AVAILABILITY_TIMEOUT
                )
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=3600,
                    step=30,
                    unit_of_measurement="seconds",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        })

        return self.async_show_form(
            step_id="ovms",
            data_schema=data_schema,
            errors=errors,
        )
