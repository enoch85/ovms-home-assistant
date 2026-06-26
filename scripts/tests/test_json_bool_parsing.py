#!/usr/bin/env python3
"""Regression test for boolean handling in parse_value.

``bool`` is a subclass of ``int``, so an ``isinstance(value, (int, float))``
check matches booleans. The dedicated ``isinstance(value, bool)`` branch sat
*after* that check and was therefore unreachable: a Python ``True``/``False``
reaching the scalar branches was returned as-is (rendered "True" for a numeric
sensor) instead of being converted to 1/0.

The fix moves the bool check ahead of the int/float check. String "true"/
"false" payloads were already handled earlier (parse_value lines ~233-236), so
this only affects already-typed boolean values; both paths are covered here.

Run standalone:  python3 scripts/tests/test_json_bool_parsing.py
Exits non-zero on failure.
"""

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
    print("OVMS parse_value boolean handling regression test")
    print("-" * 55)
    results = []

    # A real boolean on a numeric sensor must become 1/0, not Python True/False.
    _check("bool True on numeric sensor -> 1", parse_value(True, **NUM), 1, results)
    _check("bool False on numeric sensor -> 0", parse_value(False, **NUM), 0, results)

    # The common case (string payloads) keeps working.
    _check(
        'string "true" on numeric sensor -> 1', parse_value("true", **NUM), 1, results
    )
    _check(
        'string "false" on numeric sensor -> 0', parse_value("false", **NUM), 0, results
    )

    # Plain numbers are unaffected.
    _check('string "12.5" -> 12.5', parse_value("12.5", **NUM), 12.5, results)
    _check('string "1" -> 1 (int)', parse_value("1", **NUM), 1, results)

    print("-" * 55)
    if all(results):
        print(f"All {len(results)} checks passed.")
        return 0
    print(f"{results.count(False)} of {len(results)} checks FAILED.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
