#!/usr/bin/env python3
"""Regression test for restoring a sensor's stored value.

``OVMSSensor`` is always created from a live MQTT payload, yet on being added
it used to overwrite that value with Home Assistant's last *state*:

  * the last state is the DISPLAYED state, so for a user whose display unit
    differs from the native one the stored "61.16" (°F) was adopted as a native
    °C value and converted a second time - 141 °F on the dashboard until the
    next MQTT update;
  * a text state stored before a metric became numeric ("IDLE", or the raw
    tuple "229.5,0,0") was adopted by a numeric sensor, and Home Assistant then
    refused to add the entity at all.

Home Assistant's sensor documentation covers this: a sensor must not restore
from ``RestoreEntity``'s last state but extend ``RestoreSensor``, which stores
the native value and native unit. The sensor does that now, and the stored
value only fills in when the live payload gave none and it still fits the
sensor (same native unit, numeric where a number is required).

This drives the REAL ``OVMSSensor`` restore path with Home Assistant's own
``SensorExtraStoredData``.

Run standalone:  python3 scripts/tests/test_sensor_state_restore.py
Exits non-zero on failure.
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
logging.disable(logging.CRITICAL)

from homeassistant.components.sensor import RestoreSensor, SensorExtraStoredData

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


async def _restored(sensor, native_value, native_unit):
    """Run the sensor's restore with the given stored sensor data."""
    # Round-trip through the dict form, exactly as the restore store does.
    stored = SensorExtraStoredData.from_dict(
        SensorExtraStoredData(native_value, native_unit).as_dict()
    )

    async def _last_sensor_data():
        return stored

    sensor.async_get_last_sensor_data = _last_sensor_data
    await sensor._async_restore_native_value()
    return sensor.native_value


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


async def main():
    print("OVMS sensor stored-value restore regression test")
    print("-" * 55)
    results = []

    _check(
        "OVMSSensor uses Home Assistant's RestoreSensor",
        issubclass(OVMSSensor, RestoreSensor),
        True,
        results,
    )

    # A live payload always wins over the stored value.
    live = _sensor("v.e.temp", "16.2")  # defined: temperature in °C
    _check(
        "a stored value never replaces a live value",
        await _restored(live, 15.0, "°C"),
        16.2,
        results,
    )

    # No live value (empty payload): the stored value may fill in, carefully.
    _check(
        "an empty payload gives no value",
        _sensor("v.e.temp", "").native_value,
        None,
        results,
    )
    _check(
        "stored NATIVE value in the sensor's own unit is restored",
        await _restored(_sensor("v.e.temp", ""), 16.0, "°C"),
        16.0,
        results,
    )
    _check(
        "a value stored in another native unit is not mislabelled",
        await _restored(_sensor("v.e.temp", ""), 61.16, "°F"),
        None,
        results,
    )
    _check(
        "stored text is not adopted by a numeric sensor (entity would be rejected)",
        await _restored(_sensor("v.e.temp", ""), "IDLE", "°C"),
        None,
        results,
    )
    _check(
        "a stored raw tuple is not adopted by a numeric sensor",
        await _restored(_sensor("v.e.temp", ""), "229.5,0,0", "°C"),
        None,
        results,
    )

    # Nothing stored yet (first start after the upgrade): nothing to restore.
    fresh = _sensor("v.e.temp", "")

    async def _nothing():
        return None

    fresh.async_get_last_sensor_data = _nothing
    await fresh._async_restore_native_value()
    _check(
        "no stored sensor data leaves the value unset",
        fresh.native_value,
        None,
        results,
    )

    # A text sensor has no unit to get wrong.
    _check(
        "a text sensor restores its stored text",
        await _restored(_sensor("v.c.mode", ""), "standard", None),
        "standard",
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
