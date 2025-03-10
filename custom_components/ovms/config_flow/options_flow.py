"""Options flow handler for OVMS."""
import logging
import voluptuous as vol  # pylint: disable=import-error

from homeassistant.config_entries import OptionsFlow  # pylint: disable=import-error
from homeassistant.core import callback  # pylint: disable=import-error

from ..const import (
    CONF_QOS,
    CONF_TOPIC_PREFIX,
    CONF_TOPIC_STRUCTURE,
    CONF_VERIFY_SSL,
    DEFAULT_QOS,
    DEFAULT_TOPIC_PREFIX,
    DEFAULT_TOPIC_STRUCTURE,
    DEFAULT_VERIFY_SSL,
    TOPIC_STRUCTURES,
    LOGGER_NAME,
)

_LOGGER = logging.getLogger(LOGGER_NAME)


class OVMSOptionsFlow(OptionsFlow):
    """Handle OVMS options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self._config_entry = config_entry
        _LOGGER.debug("Initializing options flow for entry: %s", config_entry.entry_id)

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        _LOGGER.debug("Options flow async_step_init with input: %s", user_input)

        if user_input is not None:
            _LOGGER.debug("Saving options: %s", user_input)
            return self.async_create_entry(title="", data=user_input)

        # Get data and options from config entry
        entry_data = self._config_entry.data
        entry_options = self._config_entry.options

        # Create options schema
        options = {
            vol.Required(
                CONF_QOS,
                default=entry_options.get(
                    CONF_QOS, entry_data.get(CONF_QOS, DEFAULT_QOS)
                ),
            ): vol.In([0, 1, 2]),
            vol.Required(
                CONF_TOPIC_PREFIX,
                default=entry_options.get(
                    CONF_TOPIC_PREFIX,
                    entry_data.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
                ),
            ): str,
            vol.Optional(
                CONF_TOPIC_STRUCTURE,
                default=entry_options.get(
                    CONF_TOPIC_STRUCTURE,
                    entry_data.get(CONF_TOPIC_STRUCTURE, DEFAULT_TOPIC_STRUCTURE)
                ),
            ): vol.In(TOPIC_STRUCTURES),
            vol.Required(
                CONF_VERIFY_SSL,
                default=entry_options.get(
                    CONF_VERIFY_SSL,
                    entry_data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
                ),
            ): bool,
        }

        return self.async_show_form(step_id="init", data_schema=vol.Schema(options))
