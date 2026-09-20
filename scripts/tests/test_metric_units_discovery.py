#!/usr/bin/env python3
"""Regression test for the metric-unit discovery flow in the MQTT client.

The module is asked for its metric units once, lazily, when the first sensor
topic WITHOUT a metric definition shows up. Such topics are held back until
the answer - or its failure - is in, so an entity is never created with a
guessed unit the module could have supplied. Everything else must be created
immediately, exactly as before, and a failing query must never strand a topic.

Also covers the short numeric vector fix: a sensor that must be numeric used to
go "unknown" on a 2-3 element vector such as 3-phase currents "16.2,15.8,16.0".

This drives the REAL ``OVMSMQTTClient`` message path with a stubbed command
channel and entity factory.

Run standalone:  python3 scripts/tests/test_metric_units_discovery.py
Exits non-zero on failure.
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
logging.disable(logging.CRITICAL)

from custom_components.ovms.attribute_manager import AttributeManager
from custom_components.ovms.const import METRIC_UNITS_COMMAND
from custom_components.ovms.mqtt import OVMSMQTTClient
from custom_components.ovms.mqtt.entity_registry import EntityRegistry
from custom_components.ovms.mqtt.topic_parser import TopicParser
from custom_components.ovms.sensor.entities import OVMSSensor

CONFIG = {
    "topic_prefix": "ovms",
    "mqtt_username": "u",
    "vehicle_id": "car",
    "topic_structure": "{prefix}/{mqtt_username}/{vehicle_id}",
    "config_entry_id": "entry1",
}
BASE = "ovms/u/car/metric/"
UNDEFINED = BASE + "xks/b/pack/power"  # no vehicle module defines "xks"
DEFINED = BASE + "v/b/soc"
BINARY = BASE + "v/c/charging"


class _FakeHass:
    """Just enough of Home Assistant for the message path."""

    def __init__(self):
        self.data = {}
        self.background_tasks = []

    def async_create_background_task(self, coro, name=None):
        task = asyncio.get_running_loop().create_task(coro)
        self.background_tasks.append(task)
        return task


class _RecordingFactory:
    """Stands in for EntityFactory; records what would have been created."""

    def __init__(self):
        self.created = []

    async def async_create_entities(self, topic, payload, entity_data):
        info = entity_data.get("metric_info") or {}
        self.created.append((topic, payload, info.get("reported_unit")))


def _check(name, got, want, results):
    ok = got == want
    results.append(ok)
    print(
        f"  {'PASS' if ok else 'FAIL'}  {name}: {got!r}"
        + ("" if ok else f" != {want!r}")
    )


async def _client(command_result, gate=None):
    """Build a real client whose command channel returns ``command_result``."""
    hass = _FakeHass()
    client = OVMSMQTTClient(hass, dict(CONFIG))
    client.entity_factory = _RecordingFactory()
    commands = []

    async def _send_command(**kwargs):
        commands.append(kwargs.get("command"))
        if gate is not None:
            await gate.wait()
        return command_result

    client.async_send_command = _send_command
    return client, hass, commands


async def _stop(client):
    await client.command_handler.async_shutdown()


async def main():
    print("OVMS metric-unit discovery flow regression test")
    print("-" * 55)
    results = []

    # ---- 1) happy path: hold, ask once, release with the reported unit ---
    gate = asyncio.Event()
    reply = {"success": True, "response": f"{'xks.b.pack.power':<40.40s} 42.5kW\n"}
    client, hass, commands = await _client(reply, gate)

    await client._on_message_received(DEFINED, "81")
    await client._on_message_received(BINARY, "no")
    created = [c[0] for c in client.entity_factory.created]
    _check("defined sensor is created immediately", DEFINED in created, True, results)
    _check("binary sensor is created immediately", BINARY in created, True, results)
    _check("no query while every topic is defined", commands, [], results)

    await client._on_message_received(UNDEFINED, "42.0")
    await client._on_message_received(UNDEFINED, "42.5")  # newer payload, same topic
    await asyncio.sleep(0)
    _check(
        "undefined sensor is held back",
        UNDEFINED in [c[0] for c in client.entity_factory.created],
        False,
        results,
    )
    _check(
        "the module is asked exactly once", commands, [METRIC_UNITS_COMMAND], results
    )

    gate.set()
    await asyncio.gather(*hass.background_tasks)
    released = [c for c in client.entity_factory.created if c[0] == UNDEFINED]
    _check(
        "held topic is released once, with its LATEST payload and the reported unit",
        released,
        [(UNDEFINED, "42.5", "kW")],
        results,
    )
    _check("nothing is left waiting", client._topics_awaiting_units, {}, results)

    await client._on_message_received(BASE + "xks/b/pack/voltage", "355")
    await asyncio.sleep(0)
    _check(
        "later undefined topics are created at once, without a second query",
        (
            len(commands),
            BASE + "xks/b/pack/voltage"
            in [c[0] for c in client.entity_factory.created],
        ),
        (1, True),
        results,
    )
    await _stop(client)

    # ---- 2) every failure releases the topic with the old behaviour ------
    failures = {
        "module offline (timeout)": {
            "success": False,
            "error": "Timeout waiting for response",
        },
        "rate limited": {"success": False, "error": "Rate limit exceeded"},
        "firmware without -n (usage text)": {
            "success": True,
            "response": "Usage: metrics list [-cpst] [<metric>]",
        },
        "non-text response": {"success": True, "response": 12345},
    }
    for label, result in failures.items():
        client, hass, commands = await _client(result)
        await client._on_message_received(UNDEFINED, "42.5")
        await asyncio.gather(*hass.background_tasks)
        _check(
            f"{label}: topic still created, unit left to the guess",
            client.entity_factory.created,
            [(UNDEFINED, "42.5", None)],
            results,
        )
        await _stop(client)

    # ---- 3) shutdown while waiting creates nothing ------------------------
    gate = asyncio.Event()
    client, hass, _ = await _client(reply, gate)
    await client._on_message_received(UNDEFINED, "42.5")
    client._shutting_down = True
    gate.set()
    await asyncio.gather(*hass.background_tasks)
    _check(
        "no entity is created after shutdown began",
        client.entity_factory.created,
        [],
        results,
    )
    await _stop(client)

    # ---- 4) short numeric vectors -----------------------------------------
    def sensor(metric, payload, units=None):
        parser = TopicParser(CONFIG, EntityRegistry())
        parser.reported_units = units or {}
        topic = BASE + metric.replace(".", "/")
        parsed = parser.parse_topic(topic, payload)
        attrs = AttributeManager(CONFIG).prepare_attributes(
            topic, "x", parsed["parts"], parsed["metric_info"]
        )
        return OVMSSensor("uid", parsed["name"], topic, payload, {}, attrs, "n")

    # ("*.voltage" topics are claimed by the battery cell path, which always
    # worked; the bug was in every other numeric sensor, e.g. a current.)
    three_phase = sensor("xks.c.line.current", "16.2,15.8,16.0")
    _check(
        "numeric sensor no longer goes unknown on a 3-element vector",
        three_phase.native_value,
        16.0,
        results,
    )
    _check(
        "... the full series is kept as an attribute",
        three_phase.extra_state_attributes.get("values"),
        [16.2, 15.8, 16.0],
        results,
    )
    reported = sensor("xks.c.phases", "16.2,15.9", {"xks.c.phases": "A"})
    _check(
        "a reported unit makes a 2-element vector a numeric series",
        (reported.native_value, reported.native_unit_of_measurement),
        (16.05, "A"),
        results,
    )
    text = sensor("xks.e.some.tuple", "1,2,3")
    _check(
        "a NON-numeric sensor still shows a short tuple as text",
        text.native_value,
        "1,2,3",
        results,
    )
    long = sensor("xks.e.some.series", "1,2,3,4,5")
    _check(
        "4+ element vectors are handled as before (median)",
        long.native_value,
        3.0,
        results,
    )

    print("-" * 55)
    if all(results):
        print(f"All {len(results)} checks passed.")
        return 0
    print(f"{results.count(False)} of {len(results)} checks FAILED.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
