#!/usr/bin/env python3
"""Regression test: device_tracker imports TrackerEntity from the supported path.

Home Assistant deprecated `homeassistant.components.device_tracker.config_entry`
as the import location for `TrackerEntity` (a `DeprecatedAlias` slated for removal
in HA Core 2027.6, with `__getattr__`/`check_if_deprecated_constant` emitting the
warning). The supported import is `homeassistant.components.device_tracker`.

This guards against the deprecated `.config_entry` import path returning and
confirms the OVMS tracker still derives from the canonical `TrackerEntity`.

Run standalone:  python3 scripts/tests/test_device_tracker_import.py
Exits non-zero on failure.
"""

# pylint: disable=duplicate-code

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from homeassistant.components.device_tracker import TrackerEntity
from custom_components.ovms.device_tracker import OVMSDeviceTracker

_SRC = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "custom_components",
        "ovms",
        "device_tracker.py",
    )
)


def _check(name, cond, results):
    results.append(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


def main():
    print("OVMS device_tracker TrackerEntity import test")
    print("-" * 55)
    results = []
    with open(_SRC, encoding="utf-8") as fh:
        src = fh.read()
    _check(
        "no import of TrackerEntity from the deprecated .config_entry path",
        "device_tracker.config_entry import TrackerEntity" not in src,
        results,
    )
    _check(
        "imports TrackerEntity from the device_tracker package root",
        "from homeassistant.components.device_tracker import" in src
        and "TrackerEntity" in src,
        results,
    )
    _check(
        "OVMSDeviceTracker still derives from the canonical TrackerEntity",
        issubclass(OVMSDeviceTracker, TrackerEntity),
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
