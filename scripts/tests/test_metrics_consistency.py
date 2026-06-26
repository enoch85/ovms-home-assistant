#!/usr/bin/env python3
"""Regression test for metrics module consistency.

- ``UNIT_AMPERE_HOUR`` is now a single source of truth in const.py (it was
  duplicated in six metric modules; five copies were unused).
- The Smart ForTwo ``VEHICLE_NAME`` matches the canonical label used for its
  entity names (``VEHICLE_TOPIC_PREFIXES["xsq"]``).

Run standalone:  python3 scripts/tests/test_metrics_consistency.py
Exits non-zero on failure.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from custom_components.ovms.const import UNIT_AMPERE_HOUR, VEHICLE_TOPIC_PREFIXES
from custom_components.ovms.metrics import get_metric_by_path
from custom_components.ovms.metrics.vehicles.smart_fortwo import (
    VEHICLE_NAME as SMART_FORTWO_NAME,
)
from custom_components.ovms.metrics.vehicles.smart_ed import (
    VEHICLE_NAME as SMART_ED_NAME,
)


def _check(name, cond, results):
    results.append(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


def main():
    print("OVMS metrics consistency regression test")
    print("-" * 55)
    results = []

    _check("UNIT_AMPERE_HOUR const is 'Ah'", UNIT_AMPERE_HOUR == "Ah", results)
    _check(
        "battery Ah metric resolves the shared constant",
        get_metric_by_path("v.b.cac")["unit"] == UNIT_AMPERE_HOUR,
        results,
    )
    _check(
        "Smart ForTwo VEHICLE_NAME matches the canonical label",
        SMART_FORTWO_NAME == VEHICLE_TOPIC_PREFIXES["xsq"] == "Smart ForTwo",
        results,
    )
    _check(
        "Smart ED VEHICLE_NAME matches the canonical label",
        SMART_ED_NAME == VEHICLE_TOPIC_PREFIXES["xse"] == "Smart ED",
        results,
    )
    _check(
        "Smart ED and Smart ForTwo are distinct cars (different prefix + name)",
        SMART_ED_NAME != SMART_FORTWO_NAME
        and VEHICLE_TOPIC_PREFIXES["xse"] != VEHICLE_TOPIC_PREFIXES["xsq"],
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
