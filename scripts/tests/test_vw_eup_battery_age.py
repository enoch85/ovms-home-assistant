#!/usr/bin/env python3
"""Regression test for the VW e-Up battery-aging metrics (OVMS 3.3.006).

Firmware 3.3.006 adds cumulative battery health/aging counters:
  xvu.b.time.total / parked / parked.cold / parked.empty / parked.full /
  parked.hot  -> Days, and charged.ac / charged.dc -> Hours.
They are lifetime accumulators typed as plain numeric sensors with state_class
TOTAL and no DURATION device_class (the integration renders DURATION as a human
"Xd Yh Zm" string and clears the state_class, which would break the long-term
statistics these counters need). This test asserts every definition is typed
correctly and that a real OVMSSensor produces the numeric value with the right
unit.

Run standalone:  python3 scripts/tests/test_vw_eup_battery_age.py
Exits non-zero on failure.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import UnitOfTime

import custom_components.ovms.sensor.entities as entities_mod

from custom_components.ovms.sensor.entities import OVMSSensor
from custom_components.ovms.attribute_manager import AttributeManager
from custom_components.ovms.metrics import get_metric_by_path
from custom_components.ovms.mqtt.topic_parser import TopicParser
from custom_components.ovms.mqtt.entity_registry import EntityRegistry

DAYS_METRICS = [
    "xvu.b.time.total",
    "xvu.b.time.parked",
    "xvu.b.time.parked.cold",
    "xvu.b.time.parked.empty",
    "xvu.b.time.parked.full",
    "xvu.b.time.parked.hot",
]
HOURS_METRICS = ["xvu.b.time.charged.ac", "xvu.b.time.charged.dc"]

entities_mod.async_dispatcher_connect = lambda *a, **k: (lambda: None)


class _TestSensor(OVMSSensor):
    async def async_get_last_state(self):
        return None

    def async_write_ha_state(self):
        pass


def _check(name, cond, results):
    results.append(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


def main():
    print("VW e-Up battery-aging metrics regression test")
    print("-" * 55)
    results = []

    for path, unit in [(p, UnitOfTime.DAYS) for p in DAYS_METRICS] + [
        (p, UnitOfTime.HOURS) for p in HOURS_METRICS
    ]:
        m = get_metric_by_path(path)
        ok = (
            m is not None
            and m["state_class"] == SensorStateClass.TOTAL
            and m["unit"] == unit
            and m.get("category") == "vw_eup"
            and m.get("suggested_display_precision") == 2
            # Intentionally NOT DURATION: the integration would format the value
            # as a "Xd Yh" string and drop state_class, breaking statistics.
            and m.get("device_class") is None
        )
        _check(f"{path}: numeric TOTAL / {unit} / no device_class", ok, results)

    # Real OVMSSensor smoke test for one metric.
    path = "xvu.b.time.total"
    topic = "ovms/u/eup/metric/xvu/b/time/total"
    m = get_metric_by_path(path)
    attrs = AttributeManager({}).prepare_attributes(
        topic, m["category"], topic.split("/")[3:], m
    )
    sensor = _TestSensor(
        "ovms_test_eup_total",
        "ovms_eup_total",
        topic,
        "365.50",
        {},
        attrs,
        m["name"],
        None,
    )
    _check(
        "OVMSSensor state = 365.5 (numeric float, NOT a '365d 12h' string)",
        sensor.native_value == 365.5,
        results,
    )
    _check(
        "OVMSSensor unit=d, no device_class, state_class=total",
        sensor.native_unit_of_measurement == UnitOfTime.DAYS
        and sensor.device_class is None
        and sensor.state_class == SensorStateClass.TOTAL,
        results,
    )

    # The 48-value park-time matrix is rendered as a clean numeric-vector sensor
    # (median state + series attributes), no longer suppressed; the scalar
    # metrics still create their own sensors.
    parser = TopicParser(
        {
            "vehicle_id": "eup",
            "topic_prefix": "ovms",
            "mqtt_username": "ovmsuser",
            "topic_structure": "{prefix}/{mqtt_username}/{vehicle_id}",
        },
        EntityRegistry(),
    )
    base = "ovms/ovmsuser/eup/metric/xvu/b/time"
    _check(
        "park-time matrix topic creates a sensor (rendered, not suppressed)",
        (parser.parse_topic(f"{base}/parked/state", "0,1,2,3,4,5") or {}).get(
            "entity_type"
        )
        == "sensor",
        results,
    )
    _check(
        "scalar parked topic also creates a sensor",
        (parser.parse_topic(f"{base}/parked", "300.25") or {}).get("entity_type")
        == "sensor",
        results,
    )

    # The matrix renders cell-style: median as state, full series as attributes.
    matrix_sensor = _TestSensor(
        "ovms_test_eup_matrix",
        "ovms_eup_matrix",
        f"{base}/parked/state",
        "0,2,4,6,8,10",
        {},
        {"category": "vw_eup"},
        "Battery Time Parked State",
        None,
    )
    _check(
        "matrix sensor state is the median (5.0), not a raw vector string",
        matrix_sensor.native_value == 5.0
        and matrix_sensor.extra_state_attributes.get("count") == 6,
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
