#!/usr/bin/env python3
"""Regression test for boolean values extracted from a JSON object in parse_value.

parse_value already converts a top-level JSON boolean to 1/0 on a numeric sensor.
But a boolean carried *inside* a JSON object (e.g. ``{"state": true}`` /
``{"value": false}``) is pulled out by the dict-extraction branch, and was
returned as Python ``True``/``False`` - which HA renders as the string
"True"/"False" on a numeric sensor. The dict branch now converts it to 1/0 too,
mirroring the scalar bool handling.

Run standalone:  python3 scripts/tests/test_json_dict_bool_parsing.py
Exits non-zero on failure.
"""

# pylint: disable=duplicate-code

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from custom_components.ovms.sensor.parsers import parse_value

NUM = dict(
    device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT
)


def _check(name, got, want, results):
    ok = got == want and type(got) is type(want)
    results.append(ok)
    print(
        f"  {'PASS' if ok else 'FAIL'}  {name}: {got!r}"
        + ("" if ok else f" != {want!r}")
    )


def main():
    print("OVMS parse_value dict-boolean handling regression test")
    print("-" * 55)
    results = []

    # A boolean inside a JSON object on a numeric sensor must become 1/0.
    _check('{"state": true} -> 1', parse_value('{"state": true}', **NUM), 1, results)
    _check('{"value": false} -> 0', parse_value('{"value": false}', **NUM), 0, results)
    _check(
        '{"x": true} first-numeric -> 1', parse_value('{"x": true}', **NUM), 1, results
    )

    # Real numbers extracted from a dict are unaffected.
    _check(
        '{"value": 12.5} -> 12.5', parse_value('{"value": 12.5}', **NUM), 12.5, results
    )
    _check('{"state": 3} -> 3', parse_value('{"state": 3}', **NUM), 3, results)

    # The common scalar string path still works.
    _check('string "true" -> 1', parse_value("true", **NUM), 1, results)

    print("-" * 55)
    if all(results):
        print(f"All {len(results)} checks passed.")
        return 0
    print(f"{results.count(False)} of {len(results)} checks FAILED.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
