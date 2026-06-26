#!/usr/bin/env python3
"""Regression test for config-flow vehicle-type detection.

Smart ForTwo (453/EQ) publishes its metrics under the ``xsq`` topic prefix
(e.g. ``ovms/u/sq/metric/xsq/bms/contactor/cycles``) and
``const.VEHICLE_TOPIC_PREFIXES`` maps ``xsq`` to "Smart ForTwo". The vehicle
module previously declared ``METRIC_PREFIX = "xse."`` (the older Smart ED
module), so ``detect_vehicle_type`` never matched a real Smart ForTwo topic and
the car silently fell through to the generic profile.

This test drives the REAL ``detect_vehicle_type`` and asserts that every
declared vehicle prefix resolves to its own type (so no prefix is dead or
collides), with an explicit check for the Smart ForTwo regression, plus the
generic fallback for unknown topics.

Run standalone:  python3 scripts/tests/test_smart_fortwo_detection.py
Exits non-zero on failure.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from custom_components.ovms.config_flow.topic_discovery import detect_vehicle_type
from custom_components.ovms.const import GENERIC_VEHICLE_TYPE
from custom_components.ovms.metrics.vehicles import VEHICLE_TYPE_PREFIXES


def _topic_for(prefix: str) -> str:
    """Build a realistic MQTT metric topic for a given metric prefix."""
    # "xsq." -> "xsq/b/c"; embed under a /metric/ path like real OVMS topics.
    path = prefix.replace(".", "/") + "b/c"
    return f"ovms/u/veh/metric/{path}"


def _check(name, cond, results):
    results.append(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


def main():
    print("OVMS config-flow vehicle-type detection regression test")
    print("-" * 55)
    results = []

    # Every declared prefix must resolve to its own vehicle type. This both
    # guards the Smart ForTwo regression and proves no two prefixes collide.
    for prefix, vehicle_type in VEHICLE_TYPE_PREFIXES.items():
        detected_type, _name = detect_vehicle_type({_topic_for(prefix)})
        _check(
            f"prefix {prefix!r} -> {vehicle_type!r}",
            detected_type == vehicle_type,
            results,
        )

    # Explicit Smart ForTwo regression: a real xsq topic must detect the car.
    smart_type, _ = detect_vehicle_type({"ovms/u/sq/metric/xsq/bms/contactor/cycles"})
    _check(
        "real Smart ForTwo xsq topic detects 'smart_fortwo'",
        smart_type == "smart_fortwo",
        results,
    )

    # The stale 'xse' prefix must NOT be how Smart is detected anymore.
    _check(
        "'xse.' is no longer a declared vehicle prefix",
        "xse." not in VEHICLE_TYPE_PREFIXES,
        results,
    )

    # Unknown prefix falls back to the generic profile.
    generic_type, _ = detect_vehicle_type({"ovms/u/x/metric/zzz/b/c"})
    _check(
        "unknown topic falls back to generic",
        generic_type == GENERIC_VEHICLE_TYPE,
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
