from __future__ import annotations

import logging
import asyncio
import ssl
import functools
import voluptuous as vol
import paho.mqtt.client as mqtt

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import CONF_PORT, CONF_USERNAME, CONF_PASSWORD

from .const import DOMAIN, CONF_BROKER, CONF_TOPIC_PREFIX, CONF_QOS

_LOGGER = logging.getLogger(__name__)

PORT_OPTIONS = {
    1883: "Unencrypted (port 1883, mqtt://)",
    8883: "Encrypted (port 8883, mqtts://)",
}

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BROKER): str,
        vol.Required(CONF_PORT, default=1883): vol.In(PORT_OPTIONS),
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_TOPIC_PREFIX, default="ovms"): str,
        vol.Optional(CONF_QOS, default=1): vol.All(vol.Coerce(int), vol.Range(min=0, max=2)),
    }
)


class OVMSMQTTConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OVMS MQTT."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle the initial step."""
        _LOGGER.debug("Starting configuration flow for OVMS MQTT")

        errors = {}

        if user_input is not None:
            _LOGGER.debug("User input received: %s", user_input)

            # Validate the user input (e.g., check if the broker is reachable)
            valid, error = await self._validate_input(user_input)
            if valid:
                _LOGGER.debug("Configuration is valid, creating entry")
                return self.async_create_entry(
                    title="OVMS MQTT", data=user_input
                )
            errors["base"] = error  # Display the detailed error message in the UI
            _LOGGER.debug("Configuration validation failed: %s", errors)

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )

    async def _validate_input(self, user_input: dict) -> tuple[bool, str]:
        """Validate the user input and test the MQTT broker connection."""
        _LOGGER.debug("Validating user input: %s", user_input)

        broker = user_input[CONF_BROKER]
        port = user_input[CONF_PORT]
        username = user_input[CONF_USERNAME]
        password = user_input[CONF_PASSWORD]

        _LOGGER.debug("Testing MQTT broker connection...")
        connected, error_message = await self._test_mqtt_connection(broker, port, username, password)

        if connected:
            _LOGGER.debug("MQTT broker connection successful")
            return True, ""
        else:
            _LOGGER.error("Failed to connect to MQTT broker: %s", error_message)
            return False, error_message  # Return the detailed error message

    async def _test_mqtt_connection(self, broker: str, port: int, username: str, password: str) -> tuple[bool, str]:
        """Test the MQTT broker connection and return a tuple of (success, error_message)."""
        _LOGGER.debug("Testing connection to MQTT broker: %s:%s", broker, port)

        client = mqtt.Client()
        client.username_pw_set(username, password)

        # Configure TLS if the port is 8883
        if port == 8883:
            _LOGGER.debug("Configuring TLS for MQTT connection")
            try:
                # Offload the blocking tls_set call to a separate thread
                await self.hass.async_add_executor_job(
                    functools.partial(client.tls_set, cert_reqs=ssl.CERT_NONE),
                )
                client.tls_insecure_set(True)  # Allow insecure TLS connections
                _LOGGER.debug("TLS configuration completed successfully")
            except Exception as e:
                error_message = f"Exception while configuring TLS: {str(e)}"
                _LOGGER.error(error_message)
                return False, error_message

        connected = False
        error_message = ""

        def on_connect(client, userdata, flags, rc):
            nonlocal connected, error_message
            if rc == 0:
                _LOGGER.debug("Successfully connected to MQTT broker")
                connected = True
            else:
                error_message = f"Failed to connect to MQTT broker: {mqtt.connack_string(rc)} (code: {rc})"
                _LOGGER.error(error_message)

        client.on_connect = on_connect

        try:
            _LOGGER.debug("Attempting to connect to MQTT broker...")
            await self.hass.async_add_executor_job(client.connect, broker, port, 10)
            client.loop_start()

            # Wait for the connection to complete with timeout
            await asyncio.wait_for(self._wait_for_connection(client), timeout=10)

        except asyncio.TimeoutError:
            error_message = "Connection to MQTT broker timed out"
            _LOGGER.error(error_message)
            connected = False
        except Exception as e:
            error_message = f"Exception while connecting to MQTT broker: {str(e)}"
            _LOGGER.error(error_message)
            connected = False
        finally:
            client.loop_stop()
            client.disconnect()

        return connected, error_message

    async def _wait_for_connection(self, client):
        """Wait for the connection to be established."""
        while not client.is_connected():
            await asyncio.sleep(0.5)
