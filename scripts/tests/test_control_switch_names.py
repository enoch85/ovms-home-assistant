#!/usr/bin/env python3
"""Regression test: controllable-metric switches have a distinct display name.

Each metric in ``SWITCH_TYPES`` gets a control switch created alongside its
status sensor (e.g. ``v.c.charging`` -> a "Charging Status" binary sensor **and**
a charge on/off switch). The switch's friendly_name comes from
``SWITCH_TYPES[...]["name"]`` (``TopicParser._build_related_control_entity``).
Those entries had no ``"name"``, so the switch fell back to the status sensor's
name and both rendered identically on the device page.

This asserts every switch now defines a name that differs from its status
sensor's name.

Run standalone:  python3 scripts/tests/test_control_switch_names.py
Exits non-zero on failure.
"""

# pylint: disable=duplicate-code

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from custom_components.ovms.const import SWITCH_TYPES
from custom_components.ovms.metrics import get_metric_by_path


def _check(name, cond, results):
    results.append(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


def main():
    print("OVMS control-switch name distinctness test")
    print("-" * 55)
    results = []
    for metric_path, cfg in SWITCH_TYPES.items():
        switch_name = cfg.get("name")
        _check(
            f"{metric_path}: switch defines a non-empty name",
            bool(switch_name),
            results,
        )
        status = get_metric_by_path(metric_path)
        status_name = status.get("name") if status else None
        if status_name:
            _check(
                f"{metric_path}: switch {switch_name!r} != status {status_name!r}",
                switch_name != status_name,
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
