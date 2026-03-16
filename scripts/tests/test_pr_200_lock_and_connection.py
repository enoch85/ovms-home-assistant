"""Regression tests for PR #200 lock PIN and MQTT disconnect handling."""

from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace

import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.ovms.mqtt.connection import MQTTConnectionManager
from custom_components.ovms.sensor.lock import (
    LOCK_CODE_FORMAT,
    LOCK_PIN_SECURITY_ERROR,
    OVMSLock,
)
from custom_components.ovms.utils import is_secure_pin_connection


def _create_lock(
    command_result: dict[str, object],
    *,
    default_pin: str | None = None,
    pin_allowed: bool = True,
) -> OVMSLock:
    async def command_function(**kwargs: object) -> dict[str, object]:
        return command_result

    lock = OVMSLock(
        unique_id="test-lock",
        name="vehicle_lock",
        topic="ovms/user/car/v/e/locked",
        initial_state="no",
        device_info={},
        attributes={},
        command_function=command_function,
        hass=None,
        friendly_name="Vehicle Lock",
        lock_config={
            "lock_command": "lock",
            "unlock_command": "unlock",
        },
        default_pin=default_pin,
        pin_allowed=pin_allowed,
    )
    lock.async_write_ha_state = lambda: None
    return lock


def test_lock_command_rejects_missing_success_response() -> None:
    """A success result without a response should raise instead of crashing."""
    lock = _create_lock({"success": True, "response": None})

    with pytest.raises(
        HomeAssistantError,
        match="OVMS did not confirm the lock state change",
    ):
        asyncio.run(lock._execute_command("lock_command", True, None))

    assert lock.is_locked is False


def test_lock_command_accepts_normalized_success_response() -> None:
    """Trailing punctuation should not prevent a confirmed lock action."""
    lock = _create_lock({"success": True, "response": "Vehicle locked."})

    asyncio.run(lock._execute_command("lock_command", True, None))

    assert lock.is_locked is True
    assert lock.code_format == LOCK_CODE_FORMAT


def test_lock_command_rejects_mismatched_success_response() -> None:
    """A lock action must not accept an unlock confirmation response."""
    lock = _create_lock({"success": True, "response": "Vehicle unlocked"})

    with pytest.raises(HomeAssistantError, match="OVMS reported Vehicle unlocked"):
        asyncio.run(lock._execute_command("lock_command", True, None))


def test_lock_command_usage_response_requires_pin() -> None:
    """Usage responses without a PIN should surface a clear HA error."""
    lock = _create_lock({"success": True, "response": "Usage: lock <pin>"})

    with pytest.raises(HomeAssistantError, match="pin code is likely required"):
        asyncio.run(lock._execute_command("lock_command", True, None))


def test_lock_command_failure_raises_home_assistant_error() -> None:
    """Transport or command failures should fail the HA service call."""
    lock = _create_lock({"success": False, "error": "Timeout waiting"})

    with pytest.raises(HomeAssistantError, match="Failed to execute lock"):
        asyncio.run(lock._execute_command("lock_command", True, None))


def test_lock_command_uses_configured_default_pin_when_code_missing() -> None:
    """A configured fallback PIN should be used when the service call omits code."""
    received: dict[str, object] = {}

    async def command_function(**kwargs: object) -> dict[str, object]:
        received.update(kwargs)
        return {"success": True, "response": "Vehicle locked"}

    lock = OVMSLock(
        unique_id="test-lock",
        name="vehicle_lock",
        topic="ovms/user/car/v/e/locked",
        initial_state="no",
        device_info={},
        attributes={},
        command_function=command_function,
        hass=None,
        friendly_name="Vehicle Lock",
        lock_config={
            "lock_command": "lock",
            "unlock_command": "unlock",
        },
        default_pin="1234",
    )
    lock.async_write_ha_state = lambda: None

    asyncio.run(lock.async_lock())

    assert received["parameters"] == "1234"


def test_lock_command_prefers_explicit_code_over_configured_default_pin() -> None:
    """An explicit service-call code should override the configured fallback PIN."""
    received: dict[str, object] = {}

    async def command_function(**kwargs: object) -> dict[str, object]:
        received.update(kwargs)
        return {"success": True, "response": "Vehicle unlocked"}

    lock = OVMSLock(
        unique_id="test-lock",
        name="vehicle_lock",
        topic="ovms/user/car/v/e/locked",
        initial_state="yes",
        device_info={},
        attributes={},
        command_function=command_function,
        hass=None,
        friendly_name="Vehicle Lock",
        lock_config={
            "lock_command": "lock",
            "unlock_command": "unlock",
        },
        default_pin="1234",
    )
    lock.async_write_ha_state = lambda: None

    asyncio.run(lock.async_unlock(code="5678"))

    assert received["parameters"] == "5678"


def test_insecure_connection_hides_pin_code_format() -> None:
    """The lock entity should not advertise PIN support on insecure transports."""
    lock = _create_lock(
        {"success": True, "response": "Vehicle locked"}, pin_allowed=False
    )

    assert lock.code_format is None


def test_insecure_connection_rejects_explicit_pin_code() -> None:
    """Explicit PIN use should be rejected when the MQTT transport is not secure."""
    lock = _create_lock(
        {"success": True, "response": "Vehicle locked"},
        pin_allowed=False,
    )

    with pytest.raises(HomeAssistantError, match=re.escape(LOCK_PIN_SECURITY_ERROR)):
        asyncio.run(lock.async_lock(code="1234"))


def test_insecure_connection_rejects_configured_default_pin() -> None:
    """Stored fallback PINs should also be rejected on insecure transports."""
    lock = _create_lock(
        {"success": True, "response": "Vehicle locked"},
        default_pin="1234",
        pin_allowed=False,
    )

    with pytest.raises(HomeAssistantError, match=re.escape(LOCK_PIN_SECURITY_ERROR)):
        asyncio.run(lock.async_lock())


def test_secure_pin_connection_requires_verified_tls() -> None:
    """PIN transport should require both a secure protocol and TLS verification."""
    assert is_secure_pin_connection({"protocol": "mqtts", "verify_ssl": True})
    assert not is_secure_pin_connection({"protocol": "mqtts", "verify_ssl": False})
    assert not is_secure_pin_connection({"protocol": "mqtt", "verify_ssl": True})


def test_disconnect_with_none_reason_schedules_reconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unexpected disconnect with rc=None should still log and reconnect."""
    states: list[bool] = []
    scheduled: dict[str, object] = {}

    manager = MQTTConnectionManager(
        hass=SimpleNamespace(loop=object()),
        config={
            "topic_prefix": "ovms",
            "vehicle_id": "car",
            "mqtt_username": "user",
        },
        message_callback=lambda *_: None,
        connection_callback=states.append,
    )
    manager.client = SimpleNamespace()

    def fake_run_coroutine_threadsafe(coro: object, loop: object) -> object:
        scheduled["loop"] = loop
        scheduled["coro"] = coro
        if asyncio.iscoroutine(coro):
            coro.close()
        return object()

    monkeypatch.setattr(
        asyncio, "run_coroutine_threadsafe", fake_run_coroutine_threadsafe
    )

    manager._setup_callbacks()
    manager.client.on_disconnect(None, None, None)

    assert manager.reconnect_count == 1
    assert states == [False]
    assert scheduled["loop"] is manager.hass.loop
    assert manager._get_reason_message(None) == "Unknown reason code: None"
