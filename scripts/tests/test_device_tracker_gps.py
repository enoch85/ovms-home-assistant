#!/usr/bin/env python3
"""Regression test for the OVMS device-tracker GPS coalescing.

OVMS publishes ``v.p.latitude`` and ``v.p.longitude`` as two SEPARATE MQTT
messages. The combined device tracker must assemble them into one position
without:

  * dropping single-axis movement -- driving due east only moves longitude, so
    a tracker that waits for BOTH axes to change records nothing and the map
    draws a straight line between far-apart points (issue #223); and
  * recording a half-updated pair -- new latitude paired with stale longitude
    produces a right-angle "blocky" artifact (issue #203).

This test drives the REAL UpdateDispatcher + OVMSDeviceTracker with simulated
GPS message streams and asserts the tracker writes exactly the correct
positions. A deterministic fake event loop fires the coalescing timer between
fixes (real fixes arrive >= 1 s apart, well past GPS_COALESCE_WINDOW).

Run standalone:  python3 scripts/tests/test_device_tracker_gps.py
Exits non-zero on failure so CI catches regressions of #203 / #223.
"""

import asyncio
import os
import sys

# Make the repo root importable when run directly from scripts/tests/.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import custom_components.ovms.mqtt.update_dispatcher as ud_mod
import custom_components.ovms.mqtt.entity_factory as ef_mod
import custom_components.ovms.device_tracker as dt_mod

from custom_components.ovms.mqtt.topic_parser import TopicParser
from custom_components.ovms.mqtt.entity_registry import EntityRegistry
from custom_components.ovms.mqtt.update_dispatcher import UpdateDispatcher
from custom_components.ovms.mqtt.entity_factory import EntityFactory
from custom_components.ovms.device_tracker import OVMSDeviceTracker
from custom_components.ovms.naming_service import EntityNamingService
from custom_components.ovms.attribute_manager import AttributeManager
from custom_components.ovms.const import GPS_COALESCE_WINDOW, get_add_entities_signal

ENTRY_ID = "entry1"
CONFIG = {
    "vehicle_id": "leaf",
    "topic_prefix": "ovms",
    "mqtt_username": "user",
    "topic_structure": "{prefix}/{mqtt_username}/{vehicle_id}",
    "client_id": "ha_ovms_abc123",
    "config_entry_id": ENTRY_ID,
}
LAT_TOPIC = "ovms/user/leaf/metric/v/p/latitude"
LON_TOPIC = "ovms/user/leaf/metric/v/p/longitude"

# In-process replacement for the HA dispatcher transport.
_BUS = {}


def _connect(_hass, signal, target):
    _BUS.setdefault(signal, []).append(target)
    return lambda: None


def _send(_hass, signal, *args):
    for target in list(_BUS.get(signal, [])):
        target(*args)


ud_mod.async_dispatcher_send = _send
ef_mod.async_dispatcher_send = _send
dt_mod.async_dispatcher_connect = _connect


class _FakeTimer:
    """Cancelable handle returned by the fake loop's call_later."""

    def __init__(self, when, callback):
        self.when = when
        self.callback = callback
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class _FakeLoop:
    """Minimal call_later scheduler driven by an explicit clock."""

    def __init__(self):
        self.now = 0.0
        self.timers = []

    def call_later(self, delay, callback, *args):
        timer = _FakeTimer(self.now + delay, lambda: callback(*args))
        self.timers.append(timer)
        return timer

    def advance(self, seconds):
        target = self.now + seconds
        while True:
            due = [t for t in self.timers if not t.cancelled and t.when <= target]
            if not due:
                break
            due.sort(key=lambda t: t.when)
            timer = due[0]
            self.now = timer.when
            self.timers.remove(timer)
            timer.callback()
        self.now = target


class _FakeHass:
    def __init__(self):
        self.data = {"ovms": {"dispatched_updates": set()}}
        self.loop = _FakeLoop()


class _RecordingTracker(OVMSDeviceTracker):
    """Tracker that records the positions it would write to HA history."""

    def __init__(self, *args, writes, **kwargs):
        self._writes = writes
        super().__init__(*args, **kwargs)

    async def async_get_last_state(self):
        return None

    def async_write_ha_state(self):
        self._writes.append((round(self._latitude, 6), round(self._longitude, 6)))


async def _build():
    _BUS.clear()
    writes = []
    hass = _FakeHass()
    registry = EntityRegistry()
    attr = AttributeManager(CONFIG)
    naming = EntityNamingService(CONFIG)
    dispatcher = UpdateDispatcher(hass, registry, attr, CONFIG)
    factory = EntityFactory(hass, registry, dispatcher, CONFIG, naming, attr)
    factory.platforms_loaded = True
    parser = TopicParser(CONFIG, registry)

    holder = {}

    def on_add(data):
        if data.get("entity_type") == "device_tracker":
            holder["data"] = data

    _BUS.setdefault(get_add_entities_signal(ENTRY_ID), []).append(on_add)
    for topic, value in ((LAT_TOPIC, "59.1"), (LON_TOPIC, "10.1")):
        await factory.async_create_entities(
            topic, value, parser.parse_topic(topic, value)
        )

    data = holder["data"]
    tracker = _RecordingTracker(
        data["unique_id"],
        data["name"],
        data["topic"],
        data["payload"],
        data["device_info"],
        data["attributes"],
        hass,
        data["friendly_name"],
        naming,
        attr,
        writes=writes,
    )
    await tracker.async_added_to_hass()
    return hass, dispatcher, writes


async def _run(ticks):
    """Feed per-fix message groups; advance the clock past the coalesce window
    between fixes. Returns the list of positions the tracker recorded."""
    hass, dispatcher, writes = await _build()
    for tick in ticks:
        for kind, value in tick:
            topic = LAT_TOPIC if kind == "lat" else LON_TOPIC
            dispatcher.dispatch_update(topic, f"{value:.6f}")
        hass.loop.advance(GPS_COALESCE_WINDOW + 0.1)
    return writes


def _expected(ticks):
    """Best-known position after each fix = (latest lat, latest lon), deduped."""
    out = []
    lat = lon = None
    for tick in ticks:
        for kind, value in tick:
            if kind == "lat":
                lat = round(value, 6)
            else:
                lon = round(value, 6)
        if lat is not None and lon is not None and (not out or out[-1] != (lat, lon)):
            out.append((lat, lon))
    return out


def _check(name, ticks, results):
    written = asyncio.run(_run(ticks))
    expected = _expected(ticks)
    expected_set = set(expected)
    dropped = [p for p in expected if p not in set(written)]
    stale_mix = [p for p in written if p not in expected_set]
    ok = not dropped and not stale_mix
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"        expected {len(expected)} positions, tracker wrote {len(written)}")
    if dropped:
        print(f"        DROPPED (issue #223 straight lines): {dropped}")
    if stale_mix:
        print(f"        STALE-MIX (issue #203 blocky): {stale_mix}")


def main():
    print("OVMS device-tracker GPS coalescing regression test")
    print("-" * 55)
    results = []

    # Normal drive: latitude then longitude per fix.
    _check(
        "alternating lat,lon per fix",
        [[("lat", 59.100 + i * 0.001), ("lon", 10.100 + i * 0.001)] for i in range(5)],
        results,
    )

    # Reversed order: longitude then latitude per fix.
    _check(
        "lon-then-lat per fix",
        [[("lon", 10.100 + i * 0.001), ("lat", 59.100 + i * 0.001)] for i in range(5)],
        results,
    )

    # Drive due east: latitude static, only longitude changes (issue #223).
    _check(
        "drive east, latitude static (single-axis)",
        [[("lat", 59.100), ("lon", 10.100)]]
        + [[("lon", 10.100 + i * 0.001)] for i in range(1, 5)],
        results,
    )

    # Retained-message burst on reconnect: all lat then all lon in one window.
    _check(
        "burst redelivery (all lat, then all lon)",
        [
            [("lat", 59.100 + i * 0.001) for i in range(4)]
            + [("lon", 10.100 + i * 0.001) for i in range(4)]
        ],
        results,
    )

    # Latitude updating faster than longitude near a turn.
    _check(
        "latitude faster than longitude (turn)",
        [
            [("lat", 59.100), ("lon", 10.100)],
            [("lat", 59.101)],
            [("lat", 59.102), ("lon", 10.101)],
            [("lat", 59.103), ("lon", 10.102)],
            [("lon", 10.103)],
        ],
        results,
    )

    print("-" * 55)
    if all(results):
        print(f"All {len(results)} scenarios passed.")
        return 0
    print(f"{results.count(False)} of {len(results)} scenarios FAILED.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
