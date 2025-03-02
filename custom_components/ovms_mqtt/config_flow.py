"""Config flow for OVMS MQTT integration."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN

DATA_SCHEMA = vol.Schema(
    {
        vol.Required("broker"): str,
        vol.Required("port", default=1883): int,
        vol.Required("username"): str,
        vol.Required("password"): str,
    }
)


class OVMSMQTTConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OVMS MQTT."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Validate the user input (e.g., check if the broker is reachable)
            valid = await self._validate_input(user_input)
            if valid:
                return self.async_create_entry(
                    title="OVMS MQTT", data=user_input
                )
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )

    async def _validate_input(self, user_input: dict) -> bool:
        """Validate the user input."""
        # Add logic to validate the MQTT broker connection (optional)
        return True
