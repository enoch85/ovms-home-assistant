#!/usr/bin/env python3
"""Regression test for the metric-unit discovery flow in the MQTT client.

The module is asked for its metric units when a sensor topic WITHOUT a metric
definition shows up whose unit it has not told us yet. Such topics are held
back until the answer - or its failure - is in, so an entity is never created
with a guessed unit the module could have supplied. Everything else must be
created immediately, exactly as before, and a failing query must never strand a
topic.

OVMS publishes its metrics retained, so on a real module they all arrive while
the config entry is still being set up and no command can be sent yet: the
query has to wait for setup to complete. And the module only lists a unit for
metrics that have a value, so a metric it sets later (charge metrics while
parked) has to be asked for when its topic first shows up.

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


class _FakeEntry:
    """Config entry that records the background tasks created on it."""

    def __init__(self, background_tasks):
        self._background_tasks = background_tasks

    def async_create_background_task(self, hass, coro, name=None):
        task = asyncio.get_running_loop().create_task(coro)
        self._background_tasks.append(task)
        return task


class _FakeConfigEntries:
    def __init__(self, entry):
        self._entry = entry

    def async_get_entry(self, entry_id):
        return self._entry if entry_id == CONFIG["config_entry_id"] else None


class _FakeHass:
    """Just enough of Home Assistant for the message path."""

    def __init__(self):
        self.data = {}
        self.background_tasks = []
        self.config_entries = _FakeConfigEntries(_FakeEntry(self.background_tasks))


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


async def _client(command_result, gate=None, setup_complete=True):
    """Build a real client whose command channel returns ``command_result``.

    ``command_result`` may be a list: one result per successive command.
    """
    hass = _FakeHass()
    client = OVMSMQTTClient(hass, dict(CONFIG))
    client.entity_factory = _RecordingFactory()
    if setup_complete:
        client._setup_complete.set()
    commands = []

    async def _send_command(**kwargs):
        commands.append(kwargs.get("command"))
        if gate is not None:
            await gate.wait()
        if isinstance(command_result, list):
            return command_result[len(commands) - 1]
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
    reply = {
        "success": True,
        "response": f"{'xks.b.pack.power':<40.40s} 42.5kW\n"
        f"{'xks.b.pack.voltage':<40.40s} 355V\n"
        f"{'xks.c.late.power':<40.40s}\n",  # registered, but no value yet
    }
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
        "a later topic the module already described is created at once, no query",
        (
            len(commands),
            [c for c in client.entity_factory.created if c[0].endswith("pack/voltage")],
        ),
        (1, [(BASE + "xks/b/pack/voltage", "355", "V")]),
        results,
    )
    await _stop(client)

    # ---- 1b) a metric that had no value when the module was first asked ---
    late = BASE + "xks/c/late/power"
    later_reply = {
        "success": True,
        "response": f"{'xks.c.late.power':<40.40s} 7.2kW\n",
    }
    client, hass, commands = await _client([reply, later_reply, later_reply])
    await client._on_message_received(UNDEFINED, "42.5")
    await asyncio.gather(*hass.background_tasks)
    await client._on_message_received(late, "7.2")  # charging started
    await asyncio.gather(*hass.background_tasks)
    _check(
        "a metric without a value at first is asked for when its topic shows up",
        (
            len(commands),
            [c for c in client.entity_factory.created if c[0] == late],
        ),
        (2, [(late, "7.2", "kW")]),
        results,
    )
    client.entity_factory.created.clear()
    await client._on_message_received(late, "7.3")  # its entity was never registered
    await asyncio.gather(*hass.background_tasks)
    _check(
        "a topic never triggers a second query",
        (len(commands), [c[0] for c in client.entity_factory.created]),
        (2, [late]),
        results,
    )
    await _stop(client)

    # ---- 1c) retained topics arrive while the entry is still being set up -
    client, hass, commands = await _client(reply, setup_complete=False)
    await client._on_message_received(UNDEFINED, "42.5")
    await asyncio.sleep(0.05)
    _check(
        "no command is sent before setup is complete; the topic waits",
        (commands, client.entity_factory.created),
        ([], []),
        results,
    )
    client._setup_complete.set()
    await asyncio.gather(*hass.background_tasks)
    _check(
        "once setup is complete the module is asked and the topic released",
        (commands, client.entity_factory.created),
        ([METRIC_UNITS_COMMAND], [(UNDEFINED, "42.5", "kW")]),
        results,
    )
    await _stop(client)

    # ---- 1d) the module cannot be asked: use what it said last time ------
    class _FakeStore:
        def __init__(self):
            self.saved = []

        async def async_save(self, data):
            self.saved.append(dict(data))

    offline = {"success": False, "error": "Timeout waiting for response"}
    client, hass, commands = await _client(offline)
    client._metric_units_store = _FakeStore()
    client.topic_parser.reported_units.update({"xks.b.pack.power": "kW"})  # loaded
    await client._on_message_received(UNDEFINED, "42.5")
    _check(
        "a unit known from an earlier setup is used at once - no waiting, no flip "
        "back to the guess while the module is away",
        client.entity_factory.created,
        [(UNDEFINED, "42.5", "kW")],
        results,
    )
    await asyncio.gather(*hass.background_tasks)
    await client._on_message_received(BASE + "xks/b/pack/voltage", "355")
    await asyncio.gather(*hass.background_tasks)
    _check(
        "the module is still asked once per setup, to notice a firmware update; "
        "an unknown metric asks again",
        (len(commands), client._metric_units_store.saved),
        (2, []),
        results,
    )
    await _stop(client)

    client, hass, commands = await _client(reply)
    client._metric_units_store = _FakeStore()
    client.topic_parser.reported_units.update({"xks.b.pack.power": "W"})  # stale
    await client._on_message_received(UNDEFINED, "42.5")
    await asyncio.gather(*hass.background_tasks)
    _check(
        "a fresh answer replaces what was stored, and is saved",
        client._metric_units_store.saved,
        [{"xks.b.pack.power": "kW", "xks.b.pack.voltage": "V"}],
        results,
    )
    client._metric_units_refreshed = False
    await client._on_message_received(BASE + "xks/b/pack/voltage", "355")
    await asyncio.gather(*hass.background_tasks)
    _check(
        "an unchanged answer is not written again",
        len(client._metric_units_store.saved),
        1,
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
