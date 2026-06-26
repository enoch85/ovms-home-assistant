#!/usr/bin/env python3
"""Regression test for the v.b.consumption metric typing.

OVMS `v.b.consumption` is the *momentary* battery energy-per-distance efficiency
(firmware unit: Wh/km), not a cumulative energy total. It was typed as
`device_class=ENERGY` + `state_class=TOTAL` + `unit=Wh`, which tells Home
Assistant to treat it as an accumulating energy meter and distorts long-term
statistics.

This asserts it now uses HA's purpose-built `ENERGY_DISTANCE` device class with
`state_class=MEASUREMENT` and the `Wh/km` unit constant.

Run standalone:  python3 scripts/tests/test_battery_consumption_metric.py
Exits non-zero on failure.
"""

# pylint: disable=duplicate-code

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergyDistance

from custom_components.ovms.metrics import get_metric_by_path


def _check(name, cond, results):
    results.append(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


def main():
    print("OVMS v.b.consumption metric typing regression test")
    print("-" * 55)
    results = []

    metric = get_metric_by_path("v.b.consumption")
    _check("metric is defined", metric is not None, results)
    if metric:
        _check(
            "device_class is ENERGY_DISTANCE (HA-native energy-per-distance)",
            metric.get("device_class") == SensorDeviceClass.ENERGY_DISTANCE,
            results,
        )
        _check(
            "state_class is MEASUREMENT (required by ENERGY_DISTANCE)",
            metric.get("state_class") == SensorStateClass.MEASUREMENT,
            results,
        )
        _check(
            "unit is the HA Wh/km constant (UnitOfEnergyDistance.WATT_HOUR_PER_KM)",
            metric.get("unit") == UnitOfEnergyDistance.WATT_HOUR_PER_KM,
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
