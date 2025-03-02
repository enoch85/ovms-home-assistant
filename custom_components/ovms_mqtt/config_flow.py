"""Config flow for OVMS MQTT integration."""
from __future__ import annotations

import logging
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
            errors["base"] = error
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
        connected = await self._test_mqtt_connection(broker, port, username, password)

        if connected:
            _LOGGER.debug("MQTT broker connection successful")
            return True, ""
        else:
            _LOGGER.error("Failed to connect to MQTT broker")
            return False, "cannot_connect"

    async def _test_mqtt_connection(self, broker: str, port: int, username: str, password: str) -> bool:
        """Test the MQTT broker connection."""
        _LOGGER.debug("Testing connection to MQTT broker: %s:%s", broker, port)

        client = mqtt.Client()
        client.username_pw_set(username, password)

        connected = False

        def on_connect(client, userdata, flags, rc):
            nonlocal connected
            if rc == 0:
                _LOGGER.debug("Successfully connected to MQTT broker")
                connected = True
            else:
                _LOGGER.error("Failed to connect to MQTT broker: %s", mqtt.connack_string(rc))

        client.on_connect = on_connect

        try:
            _LOGGER.debug("Attempting to connect to MQTT broker...")
            client.connect(broker, port, keepalive=10)
            client.loop_start()

            # Wait for the connection to complete (or timeout)
            for _ in range(10):  # Wait up to 5 seconds (10 * 0.5s)
                if connected:
                    break
                await asyncio.sleep(0.5)
        except Exception as e:
            _LOGGER.error("Exception while connecting to MQTT broker: %s", str(e))
            connected = False
        finally:
            client.loop_stop()
            client.disconnect()

        return connected
