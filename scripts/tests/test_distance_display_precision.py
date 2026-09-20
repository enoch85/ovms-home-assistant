#!/usr/bin/env python3
"""Regression test: distance sensors are shown without meaningless decimals.

The integration suggested no display precision for distances, so Home Assistant
applied its own default, which is 2 decimals for km: a service distance of
12900 km read "12,900.00 km" - easily taken for far more than it is - and the
decimals of a range, odometer or service distance are always zero.

Distances now default to whole numbers (``const.DISTANCE_DISPLAY_PRECISION``).
Trip-type distances keep one decimal, because a 0.4 km trip must not read "0",
and a definition that sets its own precision is never overruled. A user's own
display precision, set in the entity settings, still wins over any suggestion.

This drives the REAL ``OVMSSensor``.

Run standalone:  python3 scripts/tests/test_distance_display_precision.py
Exits non-zero on failure.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
logging.disable(logging.CRITICAL)

from homeassistant.components.sensor import SensorDeviceClass

from custom_components.ovms.attribute_manager import AttributeManager
from custom_components.ovms.const import (
    DISTANCE_DISPLAY_PRECISION,
    TRIP_DISTANCE_DISPLAY_PRECISION,
)
from custom_components.ovms.metrics import METRIC_DEFINITIONS
from custom_components.ovms.mqtt.entity_registry import EntityRegistry
from custom_components.ovms.mqtt.topic_parser import TopicParser
from custom_components.ovms.sensor.entities import OVMSSensor

CONFIG = {
    "topic_prefix": "ovms",
    "mqtt_username": "u",
    "vehicle_id": "car",
    "topic_structure": "{prefix}/{mqtt_username}/{vehicle_id}",
}


def _sensor(metric, payload, reported_units=None):
    parser = TopicParser(CONFIG, EntityRegistry())
    parser.reported_units = reported_units or {}
    topic = "ovms/u/car/metric/" + metric.replace(".", "/")
    parsed = parser.parse_topic(topic, payload)
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
    print("OVMS distance display precision regression test")
    print("-" * 55)
    results = []

    for metric, payload in (
        ("v.e.serv.range", "12900"),
        ("v.p.odometer", "48211.3"),
        ("v.b.range.est", "112"),
        ("v.p.valet.distance", "250"),  # metres
    ):
        sensor = _sensor(metric, payload)
        _check(
            f"{metric} is shown as a whole number",
            (sensor.device_class, sensor.suggested_display_precision),
            (SensorDeviceClass.DISTANCE, DISTANCE_DISPLAY_PRECISION),
            results,
        )
    _check(
        "the value itself is untouched (only its display changes)",
        _sensor("v.p.odometer", "48211.3").native_value,
        48211.3,
        results,
    )

    _check(
        "a trip keeps one decimal",
        _sensor("v.p.trip", "0.4").suggested_display_precision,
        TRIP_DISTANCE_DISPLAY_PRECISION,
        results,
    )

    # A distance the integration has no definition for: unit from the module.
    undefined = _sensor("xks.e.service.left", "12900", {"xks.e.service.left": "km"})
    _check(
        "an undefined metric the module reports in km follows the same rule",
        (undefined.device_class, undefined.suggested_display_precision),
        (SensorDeviceClass.DISTANCE, DISTANCE_DISPLAY_PRECISION),
        results,
    )

    # Nothing but distances is affected.
    _check(
        "a definition's own precision is kept",
        _sensor("v.b.12v.voltage", "12.61").suggested_display_precision,
        METRIC_DEFINITIONS["v.b.12v.voltage"].get("suggested_display_precision"),
        results,
    )
    _check(
        "other quantities get no suggestion, as before",
        _sensor("v.b.power", "2.3").suggested_display_precision,
        None,
        results,
    )

    explicit = {
        name: info["suggested_display_precision"]
        for name, info in METRIC_DEFINITIONS.items()
        if info.get("device_class") == SensorDeviceClass.DISTANCE
        and "suggested_display_precision" in info
    }
    _check(
        "every distance definition with its own precision is a trip-type one",
        set(explicit.values()),
        {TRIP_DISTANCE_DISPLAY_PRECISION},
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
