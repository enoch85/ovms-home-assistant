#!/usr/bin/env python3
"""Regression test: one sensor per tire for tire pressure and temperature.

OVMS publishes the TPMS values as one vector per metric - ``v.t.pressure`` is
"246,256.5,233.25,243" (kPa, front left, front right, rear left, rear right).
The integration made that one sensor with the median as its state and the
values per tire as attributes ``pressure_FL`` ... ``pressure_RR``. Home
Assistant converts the unit of an entity's state, never of an attribute, so a
user who shows pressures in bar or psi still got each tire in kPa only.

``create_cell_sensors`` could already make one sensor per tire, but nothing
called it. Now a tire metric with a convertible unit (pressure, temperature)
gets one sensor per tire: unit, device class and state class come from the
metric, so Home Assistant converts them, keeps statistics and lets the user
pick bar or psi. The vector sensor and its attributes stay as they were.

This drives the REAL ``OVMSSensor`` (created from a parsed topic) and the REAL
``CellVoltageSensor`` it hands its per-tire sensors to, with the dispatcher
stubbed so the signals can be read.

Run standalone:  python3 scripts/tests/test_tire_position_sensors.py
Exits non-zero on failure.
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
logging.disable(logging.CRITICAL)

from homeassistant.components.sensor import SensorDeviceClass

from custom_components.ovms.attribute_manager import AttributeManager
from custom_components.ovms.mqtt.entity_registry import EntityRegistry
from custom_components.ovms.mqtt.topic_parser import TopicParser
from custom_components.ovms.sensor import entities
from custom_components.ovms.sensor.entities import CellVoltageSensor, OVMSSensor

CONFIG = {
    "topic_prefix": "ovms",
    "mqtt_username": "u",
    "vehicle_id": "car",
    "topic_structure": "{prefix}/{mqtt_username}/{vehicle_id}",
}
PRESSURES = "246,256.5,233.25,243"

SIGNALS = []


def _capture(_hass, signal, *args):
    SIGNALS.append((signal, args))


entities.async_dispatcher_send = _capture
entities.async_dispatcher_connect = lambda _hass, _signal, _target: None


class _Stored:
    """Stands in for the State returned by async_get_last_state()."""

    def __init__(self, state, attributes=None):
        self.state = state
        self.attributes = attributes or {}


def _sensor(metric, payload):
    topic = "ovms/u/car/metric/" + metric.replace(".", "/")
    parsed = TopicParser(CONFIG, EntityRegistry()).parse_topic(topic, payload)
    attributes = AttributeManager(CONFIG).prepare_attributes(
        topic, "x", parsed["parts"], parsed["metric_info"]
    )
    return OVMSSensor(
        "car_tire_uid",
        parsed["name"],
        topic,
        payload,
        {},
        attributes,
        parsed["metric_info"].get("name"),
    )


def _in_hass(sensor):
    """Mark the sensor as added, as the entity platform does."""
    sensor.hass = object()
    sensor.platform = object()
    return sensor


async def _added(sensor, stored=None):
    async def _last_state():
        return stored

    sensor.async_get_last_state = _last_state
    sensor.async_on_remove = lambda _remove: None
    await sensor.async_added_to_hass()
    return sensor


def _created(signals):
    return [
        args[0]["cell_sensors"]
        for _signal, args in signals
        if args and isinstance(args[0], dict)
    ]


def _check(name, got, want, results):
    ok = got == want
    results.append(ok)
    print(
        f"  {'PASS' if ok else 'FAIL'}  {name}: {got!r}"
        + ("" if ok else f" != {want!r}")
    )


async def main():
    print("OVMS per-tire sensor regression test")
    print("-" * 55)
    results = []

    # ---- which metrics get them --------------------------------------------
    for metric, want in (
        ("v.t.pressure", True),
        ("v.t.temp", True),
        ("v.t.health", False),
        ("v.t.alert", False),
        ("v.b.c.voltage", False),
    ):
        _check(
            f"{metric} gets one sensor per tire",
            _sensor(metric, "1,2,3,4")._has_tire_position_sensors(),
            want,
            results,
        )

    # ---- created when the entity is added ----------------------------------
    SIGNALS.clear()
    parent = _sensor("v.t.pressure", PRESSURES)
    _check("nothing is created before the entity is added", SIGNALS, [], results)
    _check(
        "the vector sensor keeps the per-tire attributes",
        parent.extra_state_attributes.get("pressure_FL"),
        246.0,
        results,
    )
    await _added(_in_hass(parent))
    created = _created(SIGNALS)
    _check("one signal adds the per-tire sensors", len(created), 1, results)
    configs = created[0] if created else []
    _check(
        "four sensors, one per position",
        [c["friendly_name"] for c in configs],
        [
            "Tire Pressure Front Left",
            "Tire Pressure Front Right",
            "Tire Pressure Rear Left",
            "Tire Pressure Rear Right",
        ],
        results,
    )
    _check(
        "unique IDs are distinct",
        len({c["unique_id"] for c in configs}),
        4,
        results,
    )

    # ---- the per-tire sensor converts like any pressure sensor -------------
    front_left = CellVoltageSensor(
        configs[0]["unique_id"],
        configs[0]["name"],
        configs[0]["topic"],
        configs[0]["state"],
        {},
        configs[0]["attributes"],
        configs[0]["friendly_name"],
    )
    _check(
        "device class pressure",
        front_left.device_class,
        SensorDeviceClass.PRESSURE,
        results,
    )
    _check("native unit kPa", front_left.native_unit_of_measurement, "kPa", results)
    _check("native value", front_left.native_value, 246.0, results)
    _check(
        "no unit left in the state attributes",
        "unit_of_measurement" in front_left.extra_state_attributes,
        False,
        results,
    )
    front_left._sensor_option_unit_of_measurement = "bar"
    _check(
        "with bar selected, the state is in bar",
        (front_left.unit_of_measurement, round(float(front_left.state), 4)),
        ("bar", 2.46),
        results,
    )
    await _added(front_left, _Stored("2.46"))
    _check(
        "a stored DISPLAY value (bar) is not adopted as native kPa",
        front_left.native_value,
        246.0,
        results,
    )

    # ---- updates go to the per-tire sensors --------------------------------
    SIGNALS.clear()
    parent._handle_cell_values("250,256.5,233.25,243")
    updates = [(signal, args) for signal, args in SIGNALS]
    _check("an update is sent to each tire", len(updates), 4, results)
    _check(
        "... with its own value",
        updates[0][1] if updates else None,
        (250.0,),
        results,
    )
    _check(
        "... and not created a second time",
        _created(SIGNALS),
        [],
        results,
    )

    # ---- restart before the module sends the metric ------------------------
    SIGNALS.clear()
    restarted = _sensor("v.t.pressure", "")
    await _added(
        _in_hass(restarted),
        _Stored("244.5", {"pressure_values": [246.0, 256.5, 233.25, 243.0]}),
    )
    created = _created(SIGNALS)
    _check(
        "created from the restored attributes",
        [c["state"] for c in created[0]] if created else None,
        [246.0, 256.5, 233.25, 243.0],
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
