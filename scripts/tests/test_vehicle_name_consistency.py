#!/usr/bin/env python3
"""Regression test: each vehicle's VEHICLE_NAME matches its canonical label.

The make/model label a user sees on entities comes from
``const.VEHICLE_TOPIC_PREFIXES`` (and ``metrics/patterns.py``). A vehicle
module's ``VEHICLE_NAME`` feeds the config-flow discovery display via
``metrics.vehicles.VEHICLE_TYPE_NAMES`` -> ``config_flow.detect_vehicle_type``,
so the two must agree or the setup dialog labels a car differently than its
entities.

Two modules were out of sync with their label:
  - VW e-Up:  ``"VW e-UP!"`` vs label ``"VW eUP!"``
  - MG ZS-EV: ``"MG ZS EV"`` vs label ``"MG ZS-EV"``
(Smart ForTwo's ``"Smart EQ fortwo"`` -> ``"Smart ForTwo"`` is aligned in #238,
so its prefix is skipped here to keep this change independent.)

Run standalone:  python3 scripts/tests/test_vehicle_name_consistency.py
Exits non-zero on failure.
"""

# pylint: disable=duplicate-code

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from custom_components.ovms.const import VEHICLE_TOPIC_PREFIXES
from custom_components.ovms.metrics.vehicles import (
    VEHICLE_TYPE_PREFIXES,
    VEHICLE_TYPE_NAMES,
)

# Smart ForTwo is aligned separately (its metric prefix xse->xsq in #230 and its
# VEHICLE_NAME in #238), so skip it here by vehicle type to stay independent.
DEFERRED_TYPES = {"smart_fortwo"}


def _check(name, cond, results):
    results.append(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


def main():
    print("OVMS vehicle name/label consistency test")
    print("-" * 55)
    results = []
    for metric_prefix, vehicle_type in VEHICLE_TYPE_PREFIXES.items():
        if vehicle_type in DEFERRED_TYPES:
            continue
        key = metric_prefix.rstrip(".")
        name = VEHICLE_TYPE_NAMES[vehicle_type]
        label = VEHICLE_TOPIC_PREFIXES.get(key)
        _check(
            f"{key}: VEHICLE_NAME {name!r} == label {label!r}",
            name == label,
            results,
        )
    # The two mismatches this change fixes, asserted explicitly.
    _check(
        "VW e-Up VEHICLE_NAME is 'VW eUP!'",
        VEHICLE_TYPE_NAMES["vw_eup"] == "VW eUP!",
        results,
    )
    _check(
        "MG ZS-EV VEHICLE_NAME is 'MG ZS-EV'",
        VEHICLE_TYPE_NAMES["mg_zs_ev"] == "MG ZS-EV",
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
