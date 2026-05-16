"""Support for OVMS switches."""

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from ..const import (
    CONF_LOCK_PIN,
    DOMAIN,
    LOCK_COMMAND_ERROR_PREFIX,
    LOCK_COMMAND_USAGE_PREFIX,
    LOGGER_NAME,
    OVMS_PIN_PLACEHOLDER,
    PIN_SENSITIVE_COMMANDS,
    SWITCH_TYPES,
    SIGNAL_UPDATE_ENTITY,
    get_add_entities_signal,
)
from ..entity_state import (
    SWITCH_FALSE_STATES,
    SWITCH_TRUE_STATES,
    is_boolean_state,
    parse_boolean_state,
    update_attributes_from_json,
)
from ..utils import (
    CommandFunction,
    get_entry_command_function,
    get_merged_config,
    is_secure_pin_connection,
    normalize_lock_pin,
)

from ..metrics import get_metric_by_path, get_metric_by_pattern

_LOGGER = logging.getLogger(LOGGER_NAME)

DiscoveryData = dict[str, object]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up OVMS switches based on a config entry."""
    command_function = get_entry_command_function(hass, entry)
    # Reuse the same stored lock PIN for PIN-sensitive switch commands
    # (valet/unvalet). OVMS firmware uses one device PIN for all
    # PIN-sensitive commands; gating on verified TLS mirrors the lock entity.
    config = get_merged_config(entry)
    default_lock_pin = normalize_lock_pin(config.get(CONF_LOCK_PIN))
    pin_allowed = is_secure_pin_connection(config)

    @callback
    def async_add_switch(data: DiscoveryData) -> None:
        """Add switch based on discovery data."""
        if data["entity_type"] != "switch":
            return

        _LOGGER.info("Adding switch: %s", data["name"])

        # Extract switch_config if present (for controllable metrics)
        switch_config = data.get("switch_config", {})

        # Use kwargs to reduce positional arguments
        switch = OVMSSwitch(
            unique_id=data["unique_id"],
            name=data["name"],
            topic=data["topic"],
            initial_state=data["payload"],
            device_info=data["device_info"],
            attributes=data["attributes"],
            command_function=command_function,
            hass=hass,
            friendly_name=data.get("friendly_name"),
            switch_config=switch_config,
            default_pin=default_lock_pin,
            pin_allowed=pin_allowed,
        )

        async_add_entities([switch])

    # Subscribe to discovery events
    entry.async_on_unload(
        async_dispatcher_connect(
            hass, get_add_entities_signal(entry.entry_id), async_add_switch
        )
    )


# pylint: disable=too-many-instance-attributes,too-many-arguments,abstract-method
class OVMSSwitch(SwitchEntity, RestoreEntity):
    """Representation of an OVMS switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        unique_id: str,
        name: str,
        topic: str,
        initial_state: str,
        device_info: DeviceInfo,
        attributes: dict[str, object],
        command_function: CommandFunction,
        hass: HomeAssistant | None = None,
        friendly_name: str | None = None,
        switch_config: dict[str, object] | None = None,
        default_pin: str | None = None,
        pin_allowed: bool = False,
    ) -> None:
        """Initialize the switch.

        Args:
            unique_id: Unique identifier for the entity
            name: Internal name for the entity
            topic: MQTT topic this switch is associated with
            initial_state: Initial state value from MQTT
            device_info: Device info for Home Assistant
            attributes: Extra state attributes
            command_function: Async function to send commands
            hass: Home Assistant instance
            friendly_name: User-friendly display name
            switch_config: Configuration for controllable metrics (on/off commands)
            default_pin: Stored OVMS device PIN, appended to PIN-sensitive
                commands (e.g. valet/unvalet) when present
            pin_allowed: Whether the configured MQTT transport is verified TLS,
                gating PIN usage to avoid sending it over plaintext
        """
        self._attr_unique_id = unique_id
        # Use the entity_id compatible name for internal use
        self._internal_name = name

        # Set the entity name that will display in UI - ALWAYS use friendly_name when provided
        if friendly_name:
            self._attr_name = friendly_name
        else:
            self._attr_name = name.replace("_", " ").title()

        self._topic = topic
        self._attr_device_info = device_info
        self._attr_extra_state_attributes = {
            **attributes,
            "topic": topic,
        }
        self._command_function = command_function
        # Store switch configuration for controllable metrics
        self._switch_config = switch_config or {}
        self._default_pin = normalize_lock_pin(default_pin)
        self._pin_allowed = pin_allowed

        # Determine switch type and attributes
        self._determine_switch_type()

        # Set initial state
        self._attr_is_on = self._parse_state(initial_state)

        # Try to extract additional attributes if it's JSON
        self._process_json_payload(initial_state)

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        await super().async_added_to_hass()

        # Restore previous state if available
        if (state := await self.async_get_last_state()) is not None:
            if state.state not in (None, "unavailable", "unknown"):
                self._attr_is_on = state.state == "on"

            # Restore attributes if available
            if state.attributes:
                # Don't overwrite entity attributes like icon, etc.
                saved_attributes = {
                    k: v
                    for k, v in state.attributes.items()
                    if k not in ["icon", "entity_category", "last_updated"]
                }
                self._attr_extra_state_attributes.update(saved_attributes)

        @callback
        def update_state(payload: str) -> None:
            """Update the switch state."""
            self._attr_is_on = self._parse_state(payload)

            # Try to extract additional attributes if it's JSON
            self._process_json_payload(payload)

            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_UPDATE_ENTITY}_{self.unique_id}",
                update_state,
            )
        )

    def _parse_state(self, state: str) -> bool:
        """Parse the state string to a boolean."""
        _LOGGER.debug("Parsing switch state: %s", state)
        if not is_boolean_state(state, (SWITCH_TRUE_STATES, SWITCH_FALSE_STATES)):
            _LOGGER.warning("Could not determine switch state from value: %s", state)

        return parse_boolean_state(
            state,
            (SWITCH_TRUE_STATES, SWITCH_FALSE_STATES),
        )

    def _determine_switch_type(self) -> None:
        """Determine the switch type and set icon and category.

        Prioritizes switch_config (from SWITCH_TYPES) over metric/pattern matching.
        """
        self._attr_icon = None
        self._attr_entity_category = None

        # First priority: Use switch_config if provided (from SWITCH_TYPES)
        if self._switch_config:
            if "icon" in self._switch_config:
                self._attr_icon = self._switch_config["icon"]
            if "category" in self._switch_config:
                self._attr_entity_category = self._switch_config.get("category")
            # If switch_config provided icon or category, we're done
            if "icon" in self._switch_config or "category" in self._switch_config:
                return

        # Check if attributes specify a category
        if "category" in self._attr_extra_state_attributes:
            category = self._attr_extra_state_attributes["category"]
            if category == "diagnostic":
                self._attr_entity_category = EntityCategory.DIAGNOSTIC
                return

        # Try to find matching metric by converting topic to dot notation
        topic_suffix = self._topic
        if self._topic.count("/") >= 3:  # Skip the prefix part
            parts = self._topic.split("/")
            # Find where the actual metric path starts
            for i, part in enumerate(parts):
                if part in [
                    "metric",
                    "status",
                    "notify",
                    "command",
                    "m",
                    "v",
                    "s",
                    "t",
                ]:
                    topic_suffix = "/".join(parts[i:])
                    break

        metric_path = topic_suffix.replace("/", ".")

        # Try exact match first
        metric_info = get_metric_by_path(metric_path)

        # If no exact match, try by pattern in name and topic
        if not metric_info:
            topic_parts = topic_suffix.split("/")
            name_parts = self._internal_name.split("_")
            metric_info = get_metric_by_pattern(topic_parts) or get_metric_by_pattern(
                name_parts
            )

        # Apply metric info if found
        if metric_info:
            if "icon" in metric_info:
                self._attr_icon = metric_info["icon"]
            if "entity_category" in metric_info:
                self._attr_entity_category = metric_info["entity_category"]
            return

        # Fallback: Check SWITCH_TYPES by keyword matching
        for metric_path, switch_type in SWITCH_TYPES.items():
            type_identifier = switch_type.get("type", "")
            if (
                type_identifier in self._internal_name.lower()
                or type_identifier in self._topic.lower()
            ):
                self._attr_icon = switch_type.get("icon")
                self._attr_entity_category = switch_type.get("category")
                break

    def _derive_command(self) -> str:
        """Derive the command to use for this switch (legacy fallback).

        This is used when switch_config is not provided. For configured switches,
        use the on_command/off_command from switch_config directly.
        """
        # First check if the topic gives us the command directly
        parts = self._topic.split("/")
        if "command" in parts and len(parts) > parts.index("command") + 1:
            command_idx = parts.index("command")
            if command_idx + 1 < len(parts):
                return parts[command_idx + 1]

        # Check SWITCH_TYPES by type identifier matching
        for metric_path, switch_type in SWITCH_TYPES.items():
            type_identifier = switch_type.get("type", "")
            if type_identifier in self._internal_name.lower():
                # Return the type identifier as the base command
                return type_identifier

        # Extract command from attribute if available
        if "command" in self._attr_extra_state_attributes:
            return self._attr_extra_state_attributes["command"]

        # Fall back to the base name
        command = self._internal_name.lower().replace("command_", "")
        return command

    def _process_json_payload(self, payload: str) -> None:
        """Process JSON payload to extract additional attributes."""
        update_attributes_from_json(payload, self._attr_extra_state_attributes)

    async def _execute_command(self, command_type: str) -> None:
        """Execute a switch command (on or off).

        Args:
            command_type: Either "on" or "off"
        """
        command_key = f"{command_type}_command"

        if self._switch_config.get(command_key):
            command = self._switch_config[command_key]
            # PIN-sensitive commands (lock/unlock/valet/unvalet) need an
            # argument because the OVMS firmware shell registers them with
            # min/max=1 and rejects argument-less calls with "Usage: ...".
            # Use the stored PIN when present (and only over verified TLS, to
            # match the lock entity's gate); otherwise fall back to a neutral
            # placeholder so the shell accepts the command. Vehicle modules
            # that ignore the PIN value (e.g. Fiat 500e for valet) will
            # execute the command; modules that validate the PIN will reject
            # it cleanly and we surface that via _warn_if_command_failed.
            pin_parameter = self._resolve_command_pin(command)
            if pin_parameter is not None:
                _LOGGER.debug(
                    "Turning %s switch: %s using configured command: %s "
                    "(PIN parameter appended)",
                    command_type,
                    self.name,
                    command,
                )
                result = await self._command_function(
                    command=command,
                    parameters=pin_parameter,
                )
            else:
                _LOGGER.debug(
                    "Turning %s switch: %s using configured command: %s",
                    command_type,
                    self.name,
                    command,
                )
                # Configured commands are complete (e.g., "charge start")
                result = await self._command_function(command=command)
        else:
            # Fallback to legacy behavior with derived command + parameter
            command = self._derive_command()
            _LOGGER.debug(
                "Turning %s switch: %s using derived command: %s %s",
                command_type,
                self.name,
                command,
                command_type,
            )
            result = await self._command_function(
                command=command,
                parameters=command_type,
            )

        if result["success"]:
            self._warn_if_command_failed(command, result.get("response"))
            self._attr_is_on = command_type == "on"
            self.async_write_ha_state()
        else:
            _LOGGER.error(
                "Failed to turn %s switch %s: %s",
                command_type,
                self.name,
                result.get("error"),
            )

    def _resolve_command_pin(self, command: str) -> str | None:
        """Return the PIN argument to append to the command, or None.

        For PIN-sensitive commands (lock/unlock/valet/unvalet) the OVMS shell
        requires exactly one argument. Prefer the user's stored PIN when one
        is configured over verified TLS; otherwise fall back to a neutral
        placeholder so the shell still accepts the command. Non-PIN commands
        (charge/climate) get no parameter from here.
        """
        if not command:
            return None

        first_token = command.split(maxsplit=1)[0].lower()
        if first_token not in PIN_SENSITIVE_COMMANDS:
            return None

        if self._pin_allowed and self._default_pin:
            return self._default_pin

        return OVMS_PIN_PLACEHOLDER

    def _warn_if_command_failed(self, command: str, response: object) -> None:
        """Log a hint when OVMS reports a failure for a PIN-sensitive command.

        OVMS replies with "Usage: ..." when a required argument is missing
        (should not happen now that we always send a PIN argument) or with
        "Error: ..." when the vehicle module rejected the command — most
        commonly a PIN mismatch. The MQTT round-trip is still reported as
        success, so the switch toggles optimistically; this warning is the
        only signal a user gets that the vehicle ignored the command.
        """
        if not isinstance(response, str):
            return

        normalized = response.strip()
        if not (
            normalized.startswith(LOCK_COMMAND_USAGE_PREFIX)
            or normalized.startswith(LOCK_COMMAND_ERROR_PREFIX)
        ):
            return

        first_token = command.split(maxsplit=1)[0].lower() if command else ""
        if first_token not in PIN_SENSITIVE_COMMANDS:
            return

        _LOGGER.warning(
            "OVMS rejected '%s' on switch %s: %s. The vehicle module likely "
            "requires a valid PIN. Configure a stored PIN over a verified "
            "TLS connection (mqtts:// or wss://) in the integration options "
            "to enable PIN-protected commands.",
            command,
            self.name,
            normalized,
        )

    async def async_turn_on(self, **kwargs: object) -> None:
        """Turn the switch on."""
        await self._execute_command("on")

    async def async_turn_off(self, **kwargs: object) -> None:
        """Turn the switch off."""
        await self._execute_command("off")
