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
    CONF_PORT,
    CONF_PROTOCOL,
    CONF_TOPIC_BLACKLIST,
    CONF_ENTITY_STALENESS_HOURS,
    CONF_ENABLE_STALENESS_CLEANUP,
    CONF_DELETE_STALE_HISTORY,
    DEFAULT_QOS,
    DEFAULT_TOPIC_PREFIX,
    DEFAULT_TOPIC_STRUCTURE,
    DEFAULT_VERIFY_SSL,
    DEFAULT_TOPIC_BLACKLIST,
    DEFAULT_ENTITY_STALENESS_HOURS,
    DEFAULT_ENABLE_STALENESS_CLEANUP,
    DEFAULT_DELETE_STALE_HISTORY,
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
            # Process port and SSL verification
            if "Port" in user_input:
                port_selection = user_input["Port"]

                # Set appropriate protocol and port based on selection
                if port_selection == "8883":
                    user_input[CONF_PROTOCOL] = "mqtts"
                    user_input[CONF_PORT] = 8883
                    # Use checkbox value for secure ports
                    user_input[CONF_VERIFY_SSL] = user_input.get("verify_ssl_certificate", True)
                elif port_selection == "8084":
                    user_input[CONF_PROTOCOL] = "wss"
                    user_input[CONF_PORT] = 8084
                    # Use checkbox value for secure ports
                    user_input[CONF_VERIFY_SSL] = user_input.get("verify_ssl_certificate", True)
                elif port_selection == "1883":
                    user_input[CONF_PROTOCOL] = "mqtt"
                    user_input[CONF_PORT] = 1883
                    # Force to False for non-secure ports
                    user_input[CONF_VERIFY_SSL] = False
                elif port_selection == "8083":
                    user_input[CONF_PROTOCOL] = "ws"
                    user_input[CONF_PORT] = 8083
                    # Force to False for non-secure ports
                    user_input[CONF_VERIFY_SSL] = False

                # Remove temporary keys
                del user_input["Port"]
                if "verify_ssl_certificate" in user_input:
                    del user_input["verify_ssl_certificate"]

                # Process topic blacklist (convert to a list for storage)
                if CONF_TOPIC_BLACKLIST in user_input and isinstance(user_input[CONF_TOPIC_BLACKLIST], str):
                    blacklist = [x.strip() for x in user_input[CONF_TOPIC_BLACKLIST].split(",") if x.strip()]
                    user_input[CONF_TOPIC_BLACKLIST] = blacklist

            # Process the blacklist string input
            if CONF_TOPIC_BLACKLIST in user_input and isinstance(user_input[CONF_TOPIC_BLACKLIST], str):
                blacklist_str = user_input[CONF_TOPIC_BLACKLIST]
                user_input[CONF_TOPIC_BLACKLIST] = [item.strip() for item in blacklist_str.split(',') if item.strip()]

            _LOGGER.debug("Saving options: %s", user_input)
            return self.async_create_entry(title="", data=user_input)

        # Get data and options from config entry
        entry_data = self._config_entry.data
        entry_options = self._config_entry.options

        # Determine current port selection
        current_port = entry_data.get(CONF_PORT, 8883)
        current_protocol = entry_data.get(CONF_PROTOCOL, "mqtts")

        port_selection = "8883"  # Default
        if current_port == 1883 and current_protocol == "mqtt":
            port_selection = "1883"
        elif current_port == 8083 and current_protocol == "ws":
            port_selection = "8083"
        elif current_port == 8084 and current_protocol == "wss":
            port_selection = "8084"

        # Create options schema with port selection and place SSL verification right after ports
        current_verify_ssl = entry_options.get(
            CONF_VERIFY_SSL,
            entry_data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
        )

        options = {
            vol.Required(
                "Port",
                default=port_selection
            ): vol.In({
                "1883": "TCP Port: 1883 (mqtt://)",
                "8083": "WebSocket Port: 8083 (ws://)",
                "8883": "SSL/TLS Port: 8883 (mqtts://)",
                "8084": "Secure WebSocket Port: 8084 (wss://)",
            }),
            vol.Required(
                "verify_ssl_certificate",
                default=current_verify_ssl
            ): bool,
        }

        # Add remaining options
        options.update({
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
            vol.Optional(
                CONF_TOPIC_BLACKLIST,
                default=','.join(entry_options.get(
                    CONF_TOPIC_BLACKLIST,
                    entry_data.get(CONF_TOPIC_BLACKLIST, DEFAULT_TOPIC_BLACKLIST)
                )),
                description="Comma-separated list of topics to filter out (e.g. battery.log,xrt.log)"
            ): str,
        })

        # Entity Staleness Management section - show enable toggle first as main switch
        options.update({
            vol.Optional(
                CONF_ENABLE_STALENESS_CLEANUP,
                default=entry_options.get(
                    CONF_ENABLE_STALENESS_CLEANUP,
                    entry_data.get(CONF_ENABLE_STALENESS_CLEANUP, DEFAULT_ENABLE_STALENESS_CLEANUP)
                )
            ): bool,
            vol.Optional(
                CONF_ENTITY_STALENESS_HOURS,
                default=entry_options.get(
                    CONF_ENTITY_STALENESS_HOURS,
                    entry_data.get(CONF_ENTITY_STALENESS_HOURS, DEFAULT_ENTITY_STALENESS_HOURS)
                )
            ): vol.All(int, vol.Range(min=1, max=168)),  # 1 hour to 1 week
            vol.Optional(
                CONF_DELETE_STALE_HISTORY,
                default=entry_options.get(
                    CONF_DELETE_STALE_HISTORY,
                    entry_data.get(CONF_DELETE_STALE_HISTORY, DEFAULT_DELETE_STALE_HISTORY)
                )
            ): bool,
        })

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(options),
            description_placeholders={
                "ssl_note": "data_description"
            }
        )
