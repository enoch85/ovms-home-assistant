#!/usr/bin/env python3
"""Regression test for vehicle-specific entity naming.

OVMS publishes many vehicle-specific topics (xvu/*, xsq/*, …) that have no
explicit metric definition. Those fall back to the prefix pattern in
``metrics/patterns.py`` whose ``name`` is just the bare vehicle label
("VW eUP!", "Smart ForTwo", …). ``create_friendly_name`` used to return that
label verbatim, so every undefined vehicle metric showed up as only
"VW eUP!" with no descriptor (and collided in the UI).

The fix derives a descriptor from the topic segments after the vehicle prefix,
so an undefined ``xvu/b/soc`` reads "B Soc (VW eUP!)". This test drives the real
``EntityNamingService.create_friendly_name`` and checks the fix plus the
existing naming paths (defined vehicle metric, plain metric) still work.

Run standalone:  python3 scripts/tests/test_vehicle_entity_naming.py
Exits non-zero on failure.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from custom_components.ovms.naming_service import EntityNamingService


def _parts(topic):
    """Mimic the topic parser: segments after the vehicle id."""
    return topic.split("/eup/", 1)[-1].split("/")


def _check(name, got, want, results):
    ok = got == want
    results.append(ok)
    print(
        f"  {'PASS' if ok else 'FAIL'}  {name}: {got!r}"
        + ("" if ok else f" != {want!r}")
    )


def main():
    print("OVMS vehicle-specific entity naming regression test")
    print("-" * 55)
    results = []
    svc = EntityNamingService({"vehicle_id": "eup"})

    # 1) Undefined xvu metric -> prefix pattern name is the bare label.
    topic = "ovms/u/eup/metric/xvu/b/soc"
    label_pattern = {"name": "VW eUP!", "category": "vw_eup"}
    _check(
        "undefined xvu metric gets a descriptor",
        svc.create_friendly_name(_parts(topic), label_pattern, topic, "xvu_b_soc"),
        "B Soc (VW eUP!)",
        results,
    )

    # 2) Another vehicle's undefined metric.
    topic2 = "ovms/u/eup/metric/xsq/bms/amps"
    _check(
        "undefined xsq metric gets a descriptor",
        svc.create_friendly_name(
            _parts(topic2), {"name": "Smart ForTwo"}, topic2, "xsq_bms_amps"
        ),
        "Bms Amps (Smart ForTwo)",
        results,
    )

    # 3) A DEFINED vehicle metric (name carries the label prefix) is unchanged.
    topic3 = "ovms/u/eup/metric/xvu/b/soh/total"
    _check(
        "defined vehicle metric keeps its name + single suffix",
        svc.create_friendly_name(
            _parts(topic3),
            {"name": "VW eUP! Battery Total Age"},
            topic3,
            "x",
        ),
        "Battery Total Age (VW eUP!)",
        results,
    )

    # 4) A plain (non-vehicle) metric is untouched (no suffix).
    topic4 = "ovms/u/eup/metric/v/b/soc"
    _check(
        "plain metric name is returned unchanged",
        svc.create_friendly_name(_parts(topic4), {"name": "Battery SOC"}, topic4, "x"),
        "Battery SOC",
        results,
    )

    # 5) Bare label with no usable topic parts falls back to the label.
    _check(
        "bare label with no parts falls back to the label",
        svc.create_friendly_name([], {"name": "VW eUP!"}, "", ""),
        "VW eUP!",
        results,
    )

    # 6) Issue #267: an undefined vehicle metric whose last topic segment is a
    #    generic pattern word ("power", "temp", ...) used to take that
    #    pattern's name verbatim - a bare, vehicle-less "Power" that collided
    #    with every other "*.power" topic. It is described like any other
    #    undefined vehicle metric.
    topic6 = "ovms/u/eup/metric/xsq/v/charge/bcb/power"
    generic_power = {"name": "Power", "unit": "W"}
    _check(
        "undefined vehicle metric matching a generic pattern gets a descriptor",
        svc.create_friendly_name(
            _parts(topic6), generic_power, topic6, "x", metric_defined=False
        ),
        "V Charge Bcb Power (Smart ForTwo)",
        results,
    )

    # 7) The same pattern on a topic WITHOUT a vehicle prefix is unchanged.
    topic7 = "ovms/u/eup/metric/v/x/new/power"
    _check(
        "generic pattern on a standard metric keeps the pattern name",
        svc.create_friendly_name(
            _parts(topic7), generic_power, topic7, "x", metric_defined=False
        ),
        "Power",
        results,
    )

    # 8) A DEFINED vehicle metric is never renamed by the flag's default.
    _check(
        "defined vehicle metric is unaffected by the new parameter",
        svc.create_friendly_name(
            _parts(topic6),
            {"name": "Smart ForTwo BCB Mains Power"},
            topic6,
            "x",
            metric_defined=True,
        ),
        "BCB Mains Power (Smart ForTwo)",
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
