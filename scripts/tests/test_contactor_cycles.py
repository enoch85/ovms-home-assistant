#!/usr/bin/env python3
"""Regression test for the Smart ForTwo HV contactor cycles sensor (#224).

OVMS publishes ``xsq.bms.contactor.cycles`` as a fixed-position CSV vector
``[max, now, consumed, diff, cycles_last_hour]`` where the meaningful counter
is ``now`` (remaining cycles, counts down from 200000). The default comma
handling would average all five heterogeneous elements, which is meaningless.

The metric declares ``vector_attributes`` + ``vector_state`` and the sensor's
config-driven vector path turns that into: state = ``now``, with every element
exposed as a named attribute. This test drives the REAL OVMSSensor through an
initial value and live updates and asserts that, plus that an ordinary metric
(no vector config) is unaffected.

Run standalone:  python3 scripts/tests/test_contactor_cycles.py
Exits non-zero on failure.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import custom_components.ovms.sensor.entities as entities_mod

from custom_components.ovms.sensor.entities import OVMSSensor
from custom_components.ovms.attribute_manager import AttributeManager
from custom_components.ovms.metrics import get_metric_by_path
from custom_components.ovms.const import SIGNAL_UPDATE_ENTITY

CONTACTOR_TOPIC = "ovms/u/sq/metric/xsq/bms/contactor/cycles"
CONTACTOR_PATH = "xsq.bms.contactor.cycles"
# An ordinary scalar metric (no vector config) - must be unaffected.
PLAIN_TOPIC = "ovms/u/sq/metric/xsq/bms/amps"
PLAIN_PATH = "xsq.bms.amps"

_BUS = {}


def _connect(_hass, signal, target):
    _BUS.setdefault(signal, []).append(target)
    return lambda: None


def _send(signal, payload):
    for target in list(_BUS.get(signal, [])):
        target(payload)


entities_mod.async_dispatcher_connect = _connect


class _FakeHass:
    def __init__(self):
        self.data = {}
        self.loop = None


class _TestSensor(OVMSSensor):
    async def async_get_last_state(self):
        return None

    def async_write_ha_state(self):
        pass


def _build(path, topic, initial_state):
    attr_mgr = AttributeManager({})
    metric = get_metric_by_path(path)
    assert metric is not None, f"metric {path} not found"
    parts = topic.split("/")[3:]
    attributes = attr_mgr.prepare_attributes(
        topic, metric.get("category", "unknown"), parts, metric
    )
    sensor = _TestSensor(
        unique_id=f"ovms_test_{path.replace('.', '_')}",
        name=f"ovms_{path.replace('.', '_')}",
        topic=topic,
        initial_state=initial_state,
        device_info={},
        attributes=attributes,
        friendly_name=metric.get("name"),
        hass=_FakeHass(),
    )
    return sensor, attributes


def _check(name, cond, results):
    results.append(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


async def main():
    print("OVMS contactor-cycles vector sensor regression test")
    print("-" * 55)
    results = []

    # ---- contactor cycles: initial retained value ----
    _BUS.clear()
    sensor, attrs = _build(CONTACTOR_PATH, CONTACTOR_TOPIC, "200000,198500,1500,0,3")
    await sensor.async_added_to_hass()
    _check(
        "metric declares vector config",
        attrs.get("vector_state") == "now"
        and attrs.get("vector_attributes")[1] == "now",
        results,
    )
    _check(
        "initial state = remaining 'now' (198500), not the mean",
        sensor.native_value == 198500,
        results,
    )
    a = sensor.extra_state_attributes
    _check(
        "named attributes present",
        a.get("max") == 200000
        and a.get("consumed") == 1500
        and a.get("diff") == 0
        and a.get("cycles_last_hour") == 3,
        results,
    )

    # ---- a live update reflecting cycles being consumed ----
    _send(f"{SIGNAL_UPDATE_ENTITY}_{sensor.unique_id}", "200000,198400,1600,100,5")
    _check(
        "update tracks the new remaining count (198400)",
        sensor.native_value == 198400,
        results,
    )
    _check(
        "update refreshes named attributes (diff=100, last_hour=5)",
        sensor.extra_state_attributes.get("diff") == 100
        and sensor.extra_state_attributes.get("cycles_last_hour") == 5,
        results,
    )

    # ---- no regression: an ordinary metric is untouched and the vector
    #      gate is inert when the metric declares no vector config ----
    _BUS.clear()
    plain, _ = _build(PLAIN_PATH, PLAIN_TOPIC, "12.5")
    await plain.async_added_to_hass()
    _check(
        "ordinary scalar metric unaffected (12.5)", plain.native_value == 12.5, results
    )
    _check(
        "vector gate is inert without vector config (returns False)",
        plain._try_parse_vector("1,2,3") is False,
        results,
    )

    print("-" * 55)
    if all(results):
        print(f"All {len(results)} checks passed.")
        return 0
    print(f"{results.count(False)} of {len(results)} checks FAILED.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
