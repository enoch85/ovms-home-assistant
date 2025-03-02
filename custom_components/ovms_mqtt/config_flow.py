"""Config flow for OVMS MQTT integration."""
from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PORT_OPTIONS = {
    1883: "Unencrypted (port 1883, mqtt://)",
    8883: "Encrypted (port 8883, mqtts://)",
}

DATA_SCHEMA = vol.Schema(
    {
        vol.Required("broker"): str,
        vol.Required("port", default=1883): vol.In(PORT_OPTIONS),
        vol.Required("username"): str,
        vol.Required("password"): str,
        vol.Optional("topic_prefix", default="ovms"): str,
        vol.Optional("qos", default=1): vol.All(vol.Coerce(int), vol.Range(min=0, max=2)),
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
            valid = await self._validate_input(user_input)
            if valid:
                _LOGGER.debug("Configuration is valid, creating entry")
                return self.async_create_entry(
                    title="OVMS MQTT", data=user_input
                )
            errors["base"] = "cannot_connect"
            _LOGGER.debug("Configuration validation failed: %s", errors)

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )

    async def _validate_input(self, user_input: dict) -> bool:
        """Validate the user input."""
        _LOGGER.debug("Validating user input: %s", user_input)
        # Add logic to validate the MQTT broker connection (optional)
        return True
