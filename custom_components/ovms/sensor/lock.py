"""Support for OVMS lock entities."""

import logging

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_CODE
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from ..const import (
    CONF_LOCK_PIN,
    DOMAIN,
    LOCK_CODE_FORMAT_OPTIONAL,
    LOCK_CODE_FORMAT_REQUIRED,
    LOCK_COMMAND_ERROR_PREFIX,
    LOCK_COMMAND_SUCCESS_RESPONSES,
    LOCK_COMMAND_USAGE_PREFIX,
    LOCK_PIN_FORMAT_ERROR,
    LOCK_PIN_REQUIRED_ERROR,
    LOCK_PIN_SECURITY_ERROR,
    LOGGER_NAME,
    SIGNAL_UPDATE_ENTITY,
    get_add_entities_signal,
)
from ..entity_state import (
    LOCK_FALSE_STATES,
    LOCK_TRUE_STATES,
    parse_boolean_state,
    update_attributes_from_json,
)
from ..utils import (
    CommandFunction,
    get_entry_command_function,
    get_merged_config,
    is_secure_pin_connection,
    lock_pin_contains_whitespace,
    normalize_lock_pin,
)

_LOGGER = logging.getLogger(LOGGER_NAME)

DiscoveryData = dict[str, object]


def _normalize_lock_command_response(response: object) -> str | None:
    """Normalize an OVMS lock command response for parsing."""
    if response is None:
        return None

    normalized = (
        response.strip() if isinstance(response, str) else str(response).strip()
    )
    return normalized or None


def _is_successful_lock_command_response(response: str, locked_state: bool) -> bool:
    """Check if the OVMS response confirms the lock state change.

    OVMS currently uses simple textual confirmations. Normalize case and
    trailing punctuation so minor firmware wording changes do not break the
    success path while still rejecting unrelated responses.
    """
    normalized = response.rstrip(".!").strip().lower()
    return normalized == LOCK_COMMAND_SUCCESS_RESPONSES[locked_state]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up OVMS locks based on a config entry."""
    command_function = get_entry_command_function(hass, entry)
    config = get_merged_config(entry)
    default_lock_pin = normalize_lock_pin(config.get(CONF_LOCK_PIN))
    pin_allowed = is_secure_pin_connection(config)

    @callback
    def async_add_lock(data: DiscoveryData) -> None:
        """Add lock based on discovery data."""
        if data["entity_type"] != "lock":
            return

        _LOGGER.info("Adding lock: %s", data["name"])

        lock = OVMSLock(
            unique_id=data["unique_id"],
            name=data["name"],
            topic=data["topic"],
            initial_state=data["payload"],
            device_info=data["device_info"],
            attributes=data["attributes"],
            command_function=command_function,
            hass=hass,
            friendly_name=data.get("friendly_name"),
            lock_config=data.get("lock_config", {}),
            default_pin=default_lock_pin,
            pin_allowed=pin_allowed,
        )

        async_add_entities([lock])

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, get_add_entities_signal(entry.entry_id), async_add_lock
        )
    )


class OVMSLock(LockEntity, RestoreEntity):
    """Representation of an OVMS vehicle lock."""

    _attr_has_entity_name = True

    def __init__(
        self,
        unique_id: str,
        name: str,
        topic: str,
        initial_state: object,
        device_info: DeviceInfo,
        attributes: dict[str, object],
        command_function: CommandFunction,
        hass: HomeAssistant | None = None,
        friendly_name: str | None = None,
        lock_config: dict[str, object] | None = None,
        default_pin: str | None = None,
        pin_allowed: bool = True,
    ) -> None:
        """Initialize the lock entity."""
        self._attr_unique_id = unique_id
        self._internal_name = name
        self._attr_name = friendly_name or name.replace("_", " ").title()
        self._topic = topic
        self._attr_device_info = device_info
        filtered_attributes = {
            key: value for key, value in attributes.items() if key != "invert_state"
        }
        self._attr_extra_state_attributes = {
            **filtered_attributes,
            "topic": topic,
        }
        self._command_function = command_function
        self._lock_config = lock_config or {}
        self._default_pin = normalize_lock_pin(default_pin)
        self._pin_allowed = pin_allowed
        self._attr_icon = self._lock_config.get("icon")
        self._attr_is_locked = self._parse_state(initial_state)

        update_attributes_from_json(initial_state, self._attr_extra_state_attributes)

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates and restore the last known state."""
        await super().async_added_to_hass()

        if (state := await self.async_get_last_state()) is not None:
            if state.state not in (None, "unavailable", "unknown"):
                self._attr_is_locked = state.state == "locked"

            if state.attributes:
                saved_attributes = {
                    key: value
                    for key, value in state.attributes.items()
                    if key not in ["icon", "invert_state", "last_updated"]
                }
                self._attr_extra_state_attributes.update(saved_attributes)

        @callback
        def update_state(payload: str) -> None:
            """Update the lock state."""
            self._attr_is_locked = self._parse_state(payload)
            update_attributes_from_json(payload, self._attr_extra_state_attributes)
            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_UPDATE_ENTITY}_{self.unique_id}",
                update_state,
            )
        )

    def _parse_state(self, state: object) -> bool:
        """Parse the current lock state from the MQTT payload."""
        return parse_boolean_state(
            state,
            (LOCK_TRUE_STATES, LOCK_FALSE_STATES),
        )

    @property
    def code_format(self) -> str | None:
        """Return the expected lock PIN format for Home Assistant."""
        if not self._pin_allowed:
            return None

        if self._default_pin:
            return LOCK_CODE_FORMAT_OPTIONAL

        return LOCK_CODE_FORMAT_REQUIRED

    async def _execute_command(
        self,
        command_key: str,
        locked_state: bool,
        pin: str | None,
    ) -> None:
        """Execute a lock or unlock command."""
        command = self._lock_config.get(command_key)
        if not command:
            _LOGGER.error("No %s configured for lock %s", command_key, self.name)
            raise HomeAssistantError(
                f"No {command_key.replace('_', ' ')} configured for {self.name}"
            )

        result = await self._command_function(command=command, parameters=pin)
        response = _normalize_lock_command_response(result.get("response"))

        if result.get("success"):
            # Known success confirmation from OVMS
            if response and _is_successful_lock_command_response(
                response, locked_state
            ):
                self._attr_is_locked = locked_state
                self.async_write_ha_state()
                return

            # Known error patterns — OVMS returned a usage hint or explicit error
            if response and response.startswith(LOCK_COMMAND_USAGE_PREFIX):
                _LOGGER.error(
                    "Error response received when executing %s for %s: %s",
                    command_key,
                    self.name,
                    response,
                )
                if pin is None:
                    raise HomeAssistantError("A pin code is likely required.")

                raise HomeAssistantError("OVMS command seems to be malformed.")

            if response and response.startswith(LOCK_COMMAND_ERROR_PREFIX):
                error = response[len(LOCK_COMMAND_ERROR_PREFIX) :]
                _LOGGER.error(
                    "Error response received when executing %s for %s: %s",
                    command_key,
                    self.name,
                    response,
                )
                raise HomeAssistantError(f"OVMS reported {error}")

            # Unknown or missing response but OVMS reported success.
            # Optimistically accept the state change — firmware wording
            # varies across vehicle modules and versions.
            if response:
                _LOGGER.warning(
                    "Unrecognised success response for %s on %s: %s — "
                    "accepting state change optimistically",
                    command_key,
                    self.name,
                    response,
                )
            else:
                _LOGGER.warning(
                    "Empty response for %s on %s despite success status — "
                    "accepting state change optimistically",
                    command_key,
                    self.name,
                )

            self._attr_is_locked = locked_state
            self.async_write_ha_state()
            return

        error_message = result.get("error") or "Unknown error"
        _LOGGER.error(
            "Failed to execute %s for %s: %s",
            command_key,
            self.name,
            error_message,
        )
        raise HomeAssistantError(f"Failed to execute {command}: {error_message}")

    def _resolve_lock_pin(self, code: object) -> str:
        """Resolve and validate the lock PIN for a command invocation."""
        # Security gate first — reject immediately on insecure transports
        if not self._pin_allowed:
            raise HomeAssistantError(LOCK_PIN_SECURITY_ERROR)

        pin = normalize_lock_pin(code) or self._default_pin
        if pin is None:
            raise HomeAssistantError(LOCK_PIN_REQUIRED_ERROR)
        if lock_pin_contains_whitespace(pin):
            raise HomeAssistantError(LOCK_PIN_FORMAT_ERROR)

        return pin

    async def async_lock(self, **kwargs: object) -> None:
        """Lock the vehicle."""
        pin = self._resolve_lock_pin(kwargs.get(ATTR_CODE))
        await self._execute_command("lock_command", True, pin)

    async def async_unlock(self, **kwargs: object) -> None:
        """Unlock the vehicle."""
        pin = self._resolve_lock_pin(kwargs.get(ATTR_CODE))
        await self._execute_command("unlock_command", False, pin)
