"""Options flow handler for OVMS."""

import logging

import voluptuous as vol

from homeassistant.config_entries import OptionsFlow
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from ..const import (
    CONF_HOST,
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
    DEFAULT_DELETE_STALE_HISTORY,
    DEFAULT_LOCK_PIN,
    ERROR_CANNOT_CONNECT,
    TOPIC_STRUCTURES,
    LOGGER_NAME,
    SENSITIVE_LOG_REDACTION,
    VERIFY_SSL_FIELD,
)
from ..utils import (
    get_merged_config,
    is_secure_pin_connection,
    lock_pin_contains_whitespace,
    normalize_lock_pin,
    uses_tls_transport,
)
from .mqtt_connection import PORT_SELECTOR, async_detect_broker

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
        # Note: the base OptionsFlow exposes the entry via self.config_entry;
        # don't store it again (assigning self.config_entry is deprecated).
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
            # The port in use keeps its protocol. Another port, or none, is
            # found on the broker as in the setup.
            stored = get_merged_config(self.config_entry)
            port = user_input.get(CONF_PORT)
            if port == stored.get(CONF_PORT):
                broker = stored.get(CONF_PROTOCOL), port
            else:
                broker = await async_detect_broker(self.hass, stored[CONF_HOST], port)
            if broker is None:
                # Shown again as entered, with the protocol in use
                errors["base"] = ERROR_CANNOT_CONNECT
                broker = stored.get(CONF_PROTOCOL), port
            user_input[CONF_PROTOCOL], user_input[CONF_PORT] = broker
            user_input[CONF_VERIFY_SSL] = user_input.pop(
                VERIFY_SSL_FIELD, DEFAULT_VERIFY_SSL
            ) and uses_tls_transport(user_input)

            # Process the topic blacklist (string -> deduplicated list), once.
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

        # The port in use is shown (a suggestion, so it can be cleared to be
        # detected again), and certificate verification right after it.
        current_port = current_config.get(CONF_PORT)
        current_verify_ssl = current_config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
        secure_pin_connection = is_secure_pin_connection(current_config)
        options = {
            vol.Optional(
                CONF_PORT,
                description={"suggested_value": current_port} if current_port else None,
            ): PORT_SELECTOR,
            vol.Required(VERIFY_SSL_FIELD, default=current_verify_ssl): bool,
        }

        # Add remaining options
        options.update(
            {
                # Coerce first: the frontend can submit the selected QoS as a
                # string, which bare vol.In([0, 1, 2]) would reject.
                vol.Required(
                    CONF_QOS,
                    default=entry_options.get(
                        CONF_QOS, entry_data.get(CONF_QOS, DEFAULT_QOS)
                    ),
                ): vol.All(vol.Coerce(int), vol.In([0, 1, 2])),
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
