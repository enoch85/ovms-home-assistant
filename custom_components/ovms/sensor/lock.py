"""Support for OVMS lock entities."""

import logging

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from ..const import DOMAIN, LOGGER_NAME, SIGNAL_ADD_ENTITIES, SIGNAL_UPDATE_ENTITY
from ..entity_state import (
    LOCK_FALSE_STATES,
    LOCK_TRUE_STATES,
    parse_boolean_state,
    update_attributes_from_json,
)
from ..utils import CommandFunction, get_entry_command_function

_LOGGER = logging.getLogger(LOGGER_NAME)

DiscoveryData = dict[str, object]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up OVMS locks based on a config entry."""
    command_function = get_entry_command_function(hass, entry)

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
        )

        async_add_entities([lock])

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_ADD_ENTITIES, async_add_lock)
    )


class OVMSLock(LockEntity, RestoreEntity):
    """Representation of an OVMS vehicle lock."""

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
            "last_updated": dt_util.utcnow().isoformat(),
        }
        self._command_function = command_function
        self._lock_config = lock_config or {}
        self._attr_icon = self._lock_config.get("icon")
        self._attr_is_locked = self._parse_state(initial_state)

        if hass:
            self.entity_id = async_generate_entity_id(
                "lock.{}", name.lower(), hass=hass
            )

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
                    if key not in ["icon", "invert_state"]
                }
                self._attr_extra_state_attributes.update(saved_attributes)

        @callback
        def update_state(payload: str) -> None:
            """Update the lock state."""
            self._attr_is_locked = self._parse_state(payload)
            self._attr_extra_state_attributes["last_updated"] = (
                dt_util.utcnow().isoformat()
            )
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

    async def _execute_command(self, command_key: str, locked_state: bool) -> None:
        """Execute a lock or unlock command."""
        command = self._lock_config.get(command_key)
        if not command:
            _LOGGER.error("No %s configured for lock %s", command_key, self.name)
            return

        result = await self._command_function(command=command)
        if result.get("success"):
            self._attr_is_locked = locked_state
            self.async_write_ha_state()
            return

        _LOGGER.error(
            "Failed to execute %s for %s: %s",
            command_key,
            self.name,
            result.get("error"),
        )

    async def async_lock(self, **kwargs: object) -> None:
        """Lock the vehicle."""
        await self._execute_command("lock_command", True)

    async def async_unlock(self, **kwargs: object) -> None:
        """Unlock the vehicle."""
        await self._execute_command("unlock_command", False)
