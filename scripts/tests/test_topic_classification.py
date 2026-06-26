#!/usr/bin/env python3
"""Regression test for topic -> platform classification heuristics.

Two heuristics in ``TopicParser`` historically used loose substring matches
that misclassified metrics whose topic merely *contained* a keyword:

- ``_should_be_binary_sensor`` matched binary keywords like "cool"/"fan", so a
  numeric "cooling pump SPEED" (a percentage) became an on/off binary sensor.
- ``_is_gps_metric_topic`` matched coordinate keywords like "lat" as a
  substring, so "isolation" (contains "lat") was treated as a GPS coordinate
  and lost its unit/icon.

Both now defer to the explicit metric definition / exact coordinate matching.
This test pins that behaviour while proving real binary and GPS metrics still
classify correctly.

Run standalone:  python3 scripts/tests/test_topic_classification.py
Exits non-zero on failure.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from custom_components.ovms.mqtt.topic_parser import TopicParser

_CONFIG = {
    "vehicle_id": "veh",
    "topic_prefix": "ovms",
    "mqtt_username": "u",
    "topic_structure": "{prefix}/{mqtt_username}/{vehicle_id}",
}


def _parts(metric_path):
    return ["metric"] + metric_path.split(".")


def _topic(metric_path):
    return "ovms/u/veh/metric/" + metric_path.replace(".", "/")


def _check(name, cond, results):
    results.append(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


def main():
    print("OVMS topic-classification regression test")
    print("-" * 55)
    results = []
    tp = TopicParser(dict(_CONFIG), None)

    # Numeric sensors whose topic contains a binary/coordinate keyword must NOT
    # be misclassified - they carry an explicit unit/state_class.
    for mp in (
        "xse.cepc.cooling.pump.rpm",
        "xse.cepc.cooling.fan.rpm",
        "xse.mybms.isolation",
    ):
        _check(
            f"{mp} is not a binary sensor",
            not tp._should_be_binary_sensor(_parts(mp), mp),
            results,
        )
        _check(
            f"{mp} is not a GPS/coordinate topic",
            not tp._is_gps_metric_topic(_parts(mp), mp.split(".")[-1], _topic(mp)),
            results,
        )

    # Genuine binary metrics must stay binary.
    for mp in ("xse.v.c.active", "xse.cepc.battery.heater.on"):
        _check(
            f"{mp} is still a binary sensor",
            tp._should_be_binary_sensor(_parts(mp), mp),
            results,
        )

    # Genuine coordinate metrics must stay GPS.
    _check(
        "v.p.latitude is still a GPS/coordinate topic",
        tp._is_gps_metric_topic(
            _parts("v.p.latitude"), "latitude", _topic("v.p.latitude")
        ),
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
