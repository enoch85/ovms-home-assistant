"""Config flow for Open Vehicle Monitoring System (OVMS) integration."""
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN


class OVMSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Open Vehicle Monitoring System (OVMS)."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            return self.async_create_entry(title="OVMS", data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required("broker"): str,
                vol.Required("port", default=1883): int,
                vol.Required("username"): str,
                vol.Required("password"): str,
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return OVMSOptionsFlowHandler(config_entry)


class OVMSOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Open Vehicle Monitoring System (OVMS)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Manage the options."""
        errors = {}

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options_schema = vol.Schema(
            {
                vol.Required(
                    "broker", default=self.config_entry.options.get("broker", "")
                ): str,
                vol.Required(
                    "port", default=self.config_entry.options.get("port", 1883)
                ): int,
                vol.Required(
                    "username", default=self.config_entry.options.get("username", "")
                ): str,
                vol.Required(
                    "password", default=self.config_entry.options.get("password", "")
                ): str,
            }
        )

        return self.async_show_form(
            step_id="init", data_schema=options_schema, errors=errors
        )
