"""Options flow handler for OVMS."""

import logging
import voluptuous as vol

from homeassistant.config_entries import OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from ..const import (
    CONF_LOCK_PIN,
    CONF_QOS,
    CONF_TOPIC_PREFIX,
    CONF_TOPIC_STRUCTURE,
    CONF_VERIFY_SSL,
    CONF_PORT,
    CONF_PROTOCOL,
    CONF_TOPIC_BLACKLIST,
    CONF_ENTITY_STALENESS_MANAGEMENT,
    CONF_DELETE_STALE_HISTORY,
    DEFAULT_QOS,
    DEFAULT_TOPIC_PREFIX,
    DEFAULT_TOPIC_STRUCTURE,
    DEFAULT_VERIFY_SSL,
    DEFAULT_TOPIC_BLACKLIST,
    DEFAULT_ENTITY_STALENESS_MANAGEMENT,
    DEFAULT_DELETE_STALE_HISTORY,
    DEFAULT_LOCK_PIN,
    TOPIC_STRUCTURES,
    LOGGER_NAME,
    SENSITIVE_LOG_REDACTION,
)
from ..utils import (
    is_secure_pin_connection,
    lock_pin_contains_whitespace,
    normalize_lock_pin,
)

_LOGGER = logging.getLogger(LOGGER_NAME)

SENSITIVE_OPTION_KEYS = {CONF_LOCK_PIN}


def _redact_sensitive_options(
    options: dict[str, object] | None,
) -> dict[str, object] | None:
    """Redact sensitive option values before logging."""
    if options is None:
        return None

    redacted_options: dict[str, object] = {}
    for key, value in options.items():
        if isinstance(value, dict):
            redacted_options[key] = _redact_sensitive_options(value)
            continue

        if key in SENSITIVE_OPTION_KEYS and value:
            redacted_options[key] = SENSITIVE_LOG_REDACTION
            continue

        redacted_options[key] = value

    return redacted_options


class OVMSOptionsFlow(OptionsFlow):
    """Handle OVMS options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self._config_entry = config_entry
        _LOGGER.debug("Initializing options flow for entry: %s", config_entry.entry_id)

    def _get_clean_blacklist_display(self, entry_options, entry_data):
        """Get a clean blacklist for display, replacing legacy patterns with current ones."""
        from ..const import (
            SYSTEM_TOPIC_BLACKLIST,
            COMBINED_TOPIC_BLACKLIST,
            LEGACY_TOPIC_BLACKLIST,
        )

        # Get current stored blacklist
        current_blacklist = entry_options.get(
            CONF_TOPIC_BLACKLIST,
            entry_data.get(CONF_TOPIC_BLACKLIST, DEFAULT_TOPIC_BLACKLIST),
        )

        # If it contains legacy patterns, clean it up for display
        has_legacy = any(
            pattern in LEGACY_TOPIC_BLACKLIST for pattern in current_blacklist
        )

        if has_legacy:
            # Smart cleanup: keep current system patterns + user-only patterns
            user_only_patterns = [
                pattern
                for pattern in current_blacklist
                if pattern not in COMBINED_TOPIC_BLACKLIST
            ]
            clean_blacklist = SYSTEM_TOPIC_BLACKLIST[:] + user_only_patterns
            clean_blacklist = list(dict.fromkeys(clean_blacklist))  # Remove duplicates
            _LOGGER.debug(
                "Options flow - cleaned blacklist for display: removed legacy patterns"
            )
            return ",".join(clean_blacklist)
        else:
            # No legacy patterns, just deduplicate
            clean_blacklist = list(dict.fromkeys(current_blacklist))
            return ",".join(clean_blacklist)

    def _get_effective_config(
        self,
        entry_data: dict[str, object],
        entry_options: dict[str, object],
        user_input: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Build the effective config from persisted data plus pending input."""
        effective_config = {**entry_data, **entry_options}
        if user_input:
            effective_config.update(user_input)
        return effective_config

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors: dict[str, str] = {}
        _LOGGER.debug(
            "Options flow async_step_init with input: %s",
            _redact_sensitive_options(user_input),
        )

        if user_input is not None:
            # Process port and SSL verification
            if "Port" in user_input:
                port_selection = user_input["Port"]

                # Set appropriate protocol and port based on selection
                if port_selection == "8883":
                    user_input[CONF_PROTOCOL] = "mqtts"
                    user_input[CONF_PORT] = 8883
                    # Use checkbox value for secure ports
                    user_input[CONF_VERIFY_SSL] = user_input.get(
                        "verify_ssl_certificate", True
                    )
                elif port_selection == "8084":
                    user_input[CONF_PROTOCOL] = "wss"
                    user_input[CONF_PORT] = 8084
                    # Use checkbox value for secure ports
                    user_input[CONF_VERIFY_SSL] = user_input.get(
                        "verify_ssl_certificate", True
                    )
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
                if CONF_TOPIC_BLACKLIST in user_input and isinstance(
                    user_input[CONF_TOPIC_BLACKLIST], str
                ):
                    blacklist = [
                        x.strip()
                        for x in user_input[CONF_TOPIC_BLACKLIST].split(",")
                        if x.strip()
                    ]
                    user_input[CONF_TOPIC_BLACKLIST] = blacklist

            # Process the blacklist string input
            if CONF_TOPIC_BLACKLIST in user_input and isinstance(
                user_input[CONF_TOPIC_BLACKLIST], str
            ):
                blacklist_str = user_input[CONF_TOPIC_BLACKLIST]
                # Split, strip, filter empty, and remove duplicates while preserving order
                blacklist_items = [
                    item.strip() for item in blacklist_str.split(",") if item.strip()
                ]
                user_input[CONF_TOPIC_BLACKLIST] = list(dict.fromkeys(blacklist_items))

            # Process entity staleness management - convert string selection to proper value
            if CONF_ENTITY_STALENESS_MANAGEMENT in user_input:
                staleness_selection = user_input[CONF_ENTITY_STALENESS_MANAGEMENT]
                if staleness_selection == "disabled":
                    user_input[CONF_ENTITY_STALENESS_MANAGEMENT] = None  # Disabled
                else:
                    user_input[CONF_ENTITY_STALENESS_MANAGEMENT] = int(
                        staleness_selection
                    )  # Convert to int

            # Process lock PIN mode selection
            lock_pin_mode = user_input.pop("lock_pin_mode", None)
            if lock_pin_mode == "nopin":
                user_input[CONF_LOCK_PIN] = DEFAULT_LOCK_PIN
            elif CONF_LOCK_PIN in user_input:
                lock_pin = normalize_lock_pin(user_input[CONF_LOCK_PIN])
                if lock_pin_contains_whitespace(lock_pin):
                    errors["base"] = "invalid_lock_pin"
                user_input[CONF_LOCK_PIN] = lock_pin

            if not is_secure_pin_connection(user_input):
                user_input.pop(CONF_LOCK_PIN, None)

            if not errors:
                _LOGGER.debug(
                    "Saving options: %s", _redact_sensitive_options(user_input)
                )
                return self.async_create_entry(title="", data=user_input)

        # Get current settings
        entry_data = self.config_entry.data
        entry_options = self.config_entry.options
        current_config = self._get_effective_config(
            entry_data,
            entry_options,
            user_input,
        )

        # Debug: Log what we're getting from config
        current_blacklist = entry_options.get(
            CONF_TOPIC_BLACKLIST,
            entry_data.get(CONF_TOPIC_BLACKLIST, DEFAULT_TOPIC_BLACKLIST),
        )
        _LOGGER.debug(
            "Options flow - current blacklist from config: %s", current_blacklist
        )
        _LOGGER.debug(
            "Options flow - DEFAULT_TOPIC_BLACKLIST: %s", DEFAULT_TOPIC_BLACKLIST
        )

        # Determine current port selection
        current_port = current_config.get(CONF_PORT, 8883)
        current_protocol = current_config.get(CONF_PROTOCOL, "mqtts")

        port_selection = "8883"  # Default
        if current_port == 1883 and current_protocol == "mqtt":
            port_selection = "1883"
        elif current_port == 8083 and current_protocol == "ws":
            port_selection = "8083"
        elif current_port == 8084 and current_protocol == "wss":
            port_selection = "8084"

        # Create options schema with port selection and place SSL verification right after ports
        current_verify_ssl = current_config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
        secure_pin_connection = is_secure_pin_connection(current_config)

        options = {
            vol.Required("Port", default=port_selection): vol.In(
                {
                    "1883": "TCP Port: 1883 (mqtt://)",
                    "8083": "WebSocket Port: 8083 (ws://)",
                    "8883": "SSL/TLS Port: 8883 (mqtts://)",
                    "8084": "Secure WebSocket Port: 8084 (wss://)",
                }
            ),
            vol.Required("verify_ssl_certificate", default=current_verify_ssl): bool,
        }

        # Add remaining options
        options.update(
            {
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
                        entry_data.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX),
                    ),
                ): str,
                vol.Optional(
                    CONF_TOPIC_STRUCTURE,
                    default=entry_options.get(
                        CONF_TOPIC_STRUCTURE,
                        entry_data.get(CONF_TOPIC_STRUCTURE, DEFAULT_TOPIC_STRUCTURE),
                    ),
                ): vol.In(TOPIC_STRUCTURES),
                vol.Optional(
                    CONF_TOPIC_BLACKLIST,
                    default=self._get_clean_blacklist_display(
                        entry_options, entry_data
                    ),
                    description="Topic patterns to filter out. You can add, remove, or modify any patterns including system defaults. Comma-separated list (e.g. log,gear,custom_pattern)",
                ): str,
            }
        )

        if secure_pin_connection:
            current_pin = current_config.get(CONF_LOCK_PIN, DEFAULT_LOCK_PIN) or ""
            pin_mode = "custom" if current_pin else "nopin"
            options[vol.Optional("lock_pin_mode", default=pin_mode)] = vol.In(
                {
                    "nopin": "No PIN (disabled)",
                    "custom": "Custom PIN",
                }
            )
            options[
                vol.Optional(
                    CONF_LOCK_PIN,
                    default=current_pin,
                )
            ] = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

        # Entity Staleness Management options
        current_staleness_hours = entry_options.get(
            CONF_ENTITY_STALENESS_MANAGEMENT,
            entry_data.get(CONF_ENTITY_STALENESS_MANAGEMENT, None),
        )

        # Convert stored value to display value
        if current_staleness_hours is None:
            staleness_selection = "disabled"
        elif current_staleness_hours == 2:
            staleness_selection = "2"
        elif current_staleness_hours == 12:
            staleness_selection = "12"
        elif current_staleness_hours == 72:
            staleness_selection = "72"
        elif current_staleness_hours == 168:
            staleness_selection = "168"
        else:
            staleness_selection = "disabled"  # Default for unknown values

        options.update(
            {
                vol.Optional(
                    CONF_ENTITY_STALENESS_MANAGEMENT,
                    default=staleness_selection,
                ): vol.In(
                    {
                        "disabled": "Disabled",
                        "2": "2 hours",
                        "12": "12 hours",
                        "72": "3 days",
                        "168": "1 week",
                    }
                ),
                vol.Optional(
                    CONF_DELETE_STALE_HISTORY,
                    default=entry_options.get(
                        CONF_DELETE_STALE_HISTORY,
                        entry_data.get(
                            CONF_DELETE_STALE_HISTORY, DEFAULT_DELETE_STALE_HISTORY
                        ),
                    ),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(options),
            errors=errors,
            description_placeholders={"ssl_note": "data_description"},
        )
