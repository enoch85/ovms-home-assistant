#!/usr/bin/env python3
"""Regression test for multi-vehicle OVMS command routing.

Each OVMS config entry owns one ``OVMSMQTTClient`` (one vehicle) and its own
``CommandHandler``. When a command is sent, the handler must publish over the
connection manager of *its own* entry.

The previous selection loop compared the handler's own ``vehicle_id`` against
itself for every entry::

    current_vehicle_id = vehicle_id or self.config.get(CONF_VEHICLE_ID)
    if current_vehicle_id == self.config.get(CONF_VEHICLE_ID):  # always true
        mqtt_client = data["mqtt_client"].connection_manager

so in a multi-vehicle setup it returned the **first** connected client's
connection manager regardless of which vehicle the handler belonged to (a
wrong-broker publish when vehicles use different brokers), and an explicit,
non-matching ``vehicle_id`` could never resolve.

This drives the REAL ``CommandHandler._get_connection_manager`` against a fake
``hass.data`` holding two vehicles and asserts each handler resolves its own
vehicle's connection manager.

Run standalone:  python3 scripts/tests/test_command_routing.py
Exits non-zero on failure.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from custom_components.ovms.mqtt.command_handler import CommandHandler
from custom_components.ovms.const import CONF_VEHICLE_ID, DOMAIN


class _Sentinel:
    """Stands in for a connection manager; identity is what we assert on."""

    def __init__(self, name):
        self.name = name


class _FakeClient:
    """Minimal OVMSMQTTClient stand-in with a config and connection manager."""

    def __init__(self, vehicle_id):
        self.config = {CONF_VEHICLE_ID: vehicle_id}
        self.connection_manager = _Sentinel(vehicle_id)


class _FakeHass:
    def __init__(self, data):
        self.data = data


def _check(name, cond, results):
    results.append(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


async def _make_handler(hass, vehicle_id):
    return CommandHandler(hass, {CONF_VEHICLE_ID: vehicle_id})


async def _stop(handler):
    handler._cleanup_task.cancel()
    await asyncio.gather(handler._cleanup_task, return_exceptions=True)


async def main():
    print("OVMS multi-vehicle command routing regression test")
    print("-" * 55)
    results = []

    client_a = _FakeClient("A")
    client_b = _FakeClient("B")
    # 'A' is intentionally FIRST so the old "pick the first client" bug would
    # have selected it for every handler.
    hass = _FakeHass(
        {
            DOMAIN: {
                "entry_a": {"mqtt_client": client_a},
                "entry_b": {"mqtt_client": client_b},
            }
        }
    )

    handler_b = await _make_handler(hass, "B")
    handler_a = await _make_handler(hass, "A")
    try:
        _check(
            "handler for B resolves B's connection manager (not first entry A)",
            handler_b._get_connection_manager() is client_b.connection_manager,
            results,
        )
        _check(
            "handler for A resolves A's connection manager",
            handler_a._get_connection_manager() is client_a.connection_manager,
            results,
        )
        _check(
            "explicit vehicle_id 'A' resolves A's connection manager",
            handler_b._get_connection_manager("A") is client_a.connection_manager,
            results,
        )
        _check(
            "unknown vehicle resolves to None",
            handler_b._get_connection_manager("ZZZ") is None,
            results,
        )
    finally:
        await _stop(handler_a)
        await _stop(handler_b)

    print("-" * 55)
    if all(results):
        print(f"All {len(results)} checks passed.")
        return 0
    print(f"{results.count(False)} of {len(results)} checks FAILED.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
