"""Support for OVMS switches."""
import logging
import json
from typing import Any, Callable, Dict, Optional

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from ..const import (
    DOMAIN,
    LOGGER_NAME,
    SWITCH_TYPES,
    SIGNAL_ADD_ENTITIES,
    SIGNAL_UPDATE_ENTITY,
    truncate_state_value
)

from ..metrics import get_metric_by_path, get_metric_by_pattern

_LOGGER = logging.getLogger(LOGGER_NAME)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up OVMS switches based on a config entry."""
    @callback
    def async_add_switch(data: Dict[str, Any]) -> None:
        """Add switch based on discovery data."""
        if data["entity_type"] != "switch":
            return

        _LOGGER.info("Adding switch: %s", data["name"])

        # Get the MQTT client for publishing commands
        mqtt_client = hass.data[DOMAIN][entry.entry_id]["mqtt_client"]

        # Use kwargs to reduce positional arguments
        switch = OVMSSwitch(
            unique_id=data["unique_id"],
            name=data["name"],
            topic=data["topic"],
            initial_state=data["payload"],
            device_info=data["device_info"],
            attributes=data["attributes"],
            command_function=mqtt_client.async_send_command,
            hass=hass,
            friendly_name=data.get("friendly_name"),
            on_command = data.get("on_command"),
            off_command = data.get("off_command"),
        )

        async_add_entities([switch])

    # Subscribe to discovery events
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_ADD_ENTITIES, async_add_switch)
    )


# pylint: disable=too-many-instance-attributes,too-many-arguments,abstract-method
class OVMSSwitch(SwitchEntity, RestoreEntity):
    """Representation of an OVMS switch."""

    def __init__(
        self,
        unique_id: str,
        name: str,
        topic: str,
        initial_state: str,
        device_info: DeviceInfo,
        attributes: Dict[str, Any],
        command_function: Callable,
        hass: Optional[HomeAssistant] = None,
        on_command: Optional[str] = None,
        off_command: Optional[str] = None,
        friendly_name: Optional[str] = None,
    ) -> None:
        """Initialize the switch."""
        self._attr_unique_id = unique_id
        # Use the entity_id compatible name for internal use
        self._internal_name = name

        # Set the entity name that will display in UI - ALWAYS use friendly_name when provided
        if friendly_name:
            self._attr_name = friendly_name
        else:
            self._attr_name = name.replace("_", " ").title()

        self._topic = topic
        self._on_command = on_command
        self._off_command = off_command
        self._attr_device_info = device_info
        self._attr_extra_state_attributes = {
            **attributes,
            "topic": topic,
            "last_updated": dt_util.utcnow().isoformat(),
        }
        self._command_function = command_function

        # Explicitly set entity_id - this ensures consistent naming
        if hass:
            self.entity_id = async_generate_entity_id(
                "switch.{}",
                name.lower(),
                hass=hass
            )

        # Set initial state
        self._attr_is_on = self._parse_state(initial_state)

        ### ALEX DEBUG ###
        _LOGGER.debug("Initial state for switch %s is: %s", friendly_name, self._attr_is_on)
        ##################

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
                    k: v for k, v in state.attributes.items()
                    if k not in ["icon", "entity_category"]
                }
                self._attr_extra_state_attributes.update(saved_attributes)

        @callback
        def update_state(payload: str) -> None:
            """Update the switch state."""
            # Ensure payload is properly truncated if it's a string
            if isinstance(payload, str) and len(payload) > 255:
                truncated_payload = truncate_state_value(payload)
                payload = truncated_payload if truncated_payload is not None else payload

            self._attr_is_on = self._parse_state(payload)

            # Update timestamp attribute
            now = dt_util.utcnow()
            self._attr_extra_state_attributes["last_updated"] = now.isoformat()

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

        # Try to parse as JSON first
        try:
            data = json.loads(state)

            # If JSON is a dict with a state/value field, use that
            if isinstance(data, dict):
                for key in ["state", "value", "status"]:
                    if key in data:
                        state = str(data[key])
                        break
            # If JSON is a boolean or number, use that directly
            elif isinstance(data, bool):
                return data
            elif isinstance(data, (int, float)):
                return bool(data)
            else:
                # Convert the entire JSON to string for normal parsing
                state = str(data)

        except (ValueError, json.JSONDecodeError):
            # Not JSON, continue with string parsing
            pass

        # Make sure state is truncated if needed
        if isinstance(state, str):
            truncated_state = truncate_state_value(state)
            state = truncated_state if truncated_state is not None else state

        # Check for boolean-like values in string form
        if isinstance(state, str):
            if state.lower() in ("true", "on", "yes", "1", "enabled", "active"):
                return True
            if state.lower() in ("false", "off", "no", "0", "disabled", "inactive"):
                return False

        # Try numeric comparison for anything else
        try:
            return float(state) > 0
        except (ValueError, TypeError):
            _LOGGER.warning("Could not determine switch state from value: %s", state)
            return False

    def _process_json_payload(self, payload: str) -> None:
        """Process JSON payload to extract additional attributes."""
        try:
            # Ensure payload is properly truncated if it's a string
            if isinstance(payload, str) and len(payload) > 255:
                truncated_payload = truncate_state_value(payload)
                payload = truncated_payload if truncated_payload is not None else payload

            json_data = json.loads(payload)
            if isinstance(json_data, dict):
                # Add useful attributes from the data
                for key, value in json_data.items():
                    if (key not in ["value", "state", "status"] and
                            key not in self._attr_extra_state_attributes):
                        self._attr_extra_state_attributes[key] = value

                # If there's a timestamp in the JSON, use it
                if "timestamp" in json_data:
                    self._attr_extra_state_attributes["device_timestamp"] = json_data["timestamp"]

        except (ValueError, json.JSONDecodeError):
            # Not JSON, that's fine
            pass

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        _LOGGER.debug("Turning on switch: %s using command: %s", self.name, self._on_command)

        # Send the command to the vehicle
        result = await self._command_function(
            command=self._on_command,
            parameters="",
        )

        if not result.get("success", False):
            _LOGGER.error(
                "Failed to turn on switch %s: %s", self.name, result.get("error")
            )
        # Do NOT set self._attr_is_on here; the switch state will be updated
        # automatically via the metric through update_state

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        _LOGGER.debug("Turning off switch: %s using command: %s", self.name, self._off_command)

        # Send the command to the vehicle
        result = await self._command_function(
            command=self._off_command,
            parameters="",
        )

        if not result.get("success", False):
            _LOGGER.error(
                "Failed to turn off switch %s: %s", self.name, result.get("error")
            )
        # Do NOT set self._attr_is_on here; the switch state will be updated
        # automatically via the metric through update_state

