#!/usr/bin/env python3
"""Regression test for restoring a sensor's stored state.

``OVMSSensor`` is always created from a live MQTT payload, yet on being added
it used to overwrite that value with whatever Home Assistant had stored:

  * Home Assistant stores the DISPLAYED state, so for a user whose display unit
    differs from the native one the stored "61.16" (°F) was adopted as a native
    °C value and converted a second time - 141 °F on the dashboard until the
    next MQTT update;
  * a text state stored before a metric became numeric ("IDLE", or the raw
    tuple "229.5,0,0") was adopted by a numeric sensor, and Home Assistant then
    refused to add the entity at all.

The stored state may now only fill in when the live payload gave no value, and
for a numeric sensor only when it is a number in the sensor's own unit.

This drives the REAL ``OVMSSensor._can_restore_state``.

Run standalone:  python3 scripts/tests/test_sensor_state_restore.py
Exits non-zero on failure.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
logging.disable(logging.CRITICAL)

from custom_components.ovms.attribute_manager import AttributeManager
from custom_components.ovms.mqtt.entity_registry import EntityRegistry
from custom_components.ovms.mqtt.topic_parser import TopicParser
from custom_components.ovms.sensor.entities import OVMSSensor

CONFIG = {
    "topic_prefix": "ovms",
    "mqtt_username": "u",
    "vehicle_id": "car",
    "topic_structure": "{prefix}/{mqtt_username}/{vehicle_id}",
}


class _Stored:
    """Stands in for the State returned by async_get_last_state()."""

    def __init__(self, state, unit=None):
        self.state = state
        self.attributes = {"unit_of_measurement": unit} if unit else {}


def _sensor(metric, payload):
    topic = "ovms/u/car/metric/" + metric.replace(".", "/")
    parsed = TopicParser(CONFIG, EntityRegistry()).parse_topic(topic, payload)
    attributes = AttributeManager(CONFIG).prepare_attributes(
        topic, "x", parsed["parts"], parsed["metric_info"]
    )
    return OVMSSensor("uid", parsed["name"], topic, payload, {}, attributes, "n")


def _check(name, got, want, results):
    ok = got == want
    results.append(ok)
    print(
        f"  {'PASS' if ok else 'FAIL'}  {name}: {got!r}"
        + ("" if ok else f" != {want!r}")
    )


def main():
    print("OVMS sensor stored-state restore regression test")
    print("-" * 55)
    results = []

    # A live payload always wins over the stored state.
    live = _sensor("v.e.temp", "16.2")  # defined: temperature in °C
    _check("sensor holds the live value", live.native_value, 16.2, results)
    _check(
        "a stored state never replaces a live value",
        live._can_restore_state(_Stored("16.0", "°C")),
        False,
        results,
    )

    # No live value (empty payload): the stored state may fill in, carefully.
    empty = _sensor("v.e.temp", "")
    _check("an empty payload gives no value", empty.native_value, None, results)
    _check(
        "stored number in the sensor's own unit is restored",
        empty._can_restore_state(_Stored("16.0", "°C")),
        True,
        results,
    )
    _check(
        "stored number in a DISPLAY unit is not adopted as native (no double conversion)",
        empty._can_restore_state(_Stored("61.16", "°F")),
        False,
        results,
    )
    _check(
        "stored text is not adopted by a numeric sensor (entity would be rejected)",
        empty._can_restore_state(_Stored("IDLE")),
        False,
        results,
    )
    _check(
        "a stored raw tuple is not adopted by a numeric sensor",
        empty._can_restore_state(_Stored("229.5,0,0", "V")),
        False,
        results,
    )

    # A text sensor has no unit to get wrong: restoring stays as it was.
    text = _sensor("v.c.mode", "")  # defined, no device/state class
    _check(
        "a text sensor still restores its stored state",
        text._can_restore_state(_Stored("standard")),
        True,
        results,
    )

    print("-" * 55)
    if all(results):
        print(f"All {len(results)} checks passed.")
        return 0
    print(f"{results.count(False)} of {len(results)} checks FAILED.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
