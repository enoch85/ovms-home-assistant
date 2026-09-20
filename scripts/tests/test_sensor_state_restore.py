#!/usr/bin/env python3
"""Regression test: a sensor's value comes from the module, never from storage.

``OVMSSensor`` is always created from a live MQTT payload, yet on being added
it used to overwrite that value with Home Assistant's last *state*:

  * the last state is the DISPLAYED state, so for a user whose display unit
    differs from the native one the stored "61.16" (°F) was adopted as a native
    °C value and converted a second time - 136 °F on the dashboard until the
    next MQTT update;
  * a text state stored before a metric became numeric ("IDLE", or the raw
    tuple "229.5,0,0") was adopted by a numeric sensor, and Home Assistant then
    refused to add the entity at all.

v1.9.0 answered that by storing the native value (``RestoreSensor``), which was
worse: Home Assistant writes the restore data of EVERY entity to one file, as
JSON that only takes integers fitting 64 bits. OVMS publishes identifiers that
do not fit - a SIM's ICCID has 19-20 digits, and the parser turns an all-digit
payload into a Python int - so one such sensor made the whole
``core.restore_state`` write fail, for all integrations:
"Bad data at $.data[N].extra_data.native_value=89000000000000000001".

The value needs no storage at all: OVMS publishes retained, and the startup
metric refresh asks for what is missing. So the stored state is never adopted
and no value is handed to Home Assistant for storing. Attributes are still
restored, as before.

This drives the REAL ``OVMSSensor.async_added_to_hass`` with a stubbed last
state, and Home Assistant's own JSON encoder.

Run standalone:  python3 scripts/tests/test_sensor_state_restore.py
Exits non-zero on failure.
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
logging.disable(logging.CRITICAL)

from homeassistant.components.sensor import RestoreSensor
from homeassistant.helpers.json import json_bytes

from custom_components.ovms.attribute_manager import AttributeManager
from custom_components.ovms.mqtt.entity_registry import EntityRegistry
from custom_components.ovms.mqtt.topic_parser import TopicParser
from custom_components.ovms.sensor.entities import OVMSSensor

CONFIG = {
    "topic_prefix": "ovms",
    "mqtt_username": "u",
    "vehicle_id": "car",
    "topic_structure": "{prefix}/{mqtt_username}/{vehicle_id}",
}
ICCID = "89000000000000000001"  # 20 digits: does not fit 64 bits


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
    return OVMSSensor("uid", parsed["name"], topic, payload, {}, attributes, "n")


async def _added(sensor, stored):
    """Run the sensor's real async_added_to_hass with ``stored`` as last state."""

    async def _last_state():
        return stored

    sensor.async_get_last_state = _last_state
    await sensor.async_added_to_hass()
    return sensor


def _check(name, got, want, results):
    ok = got == want
    results.append(ok)
    print(
        f"  {'PASS' if ok else 'FAIL'}  {name}: {got!r}"
        + ("" if ok else f" != {want!r}")
    )


async def main():
    print("OVMS sensor value-comes-from-the-module regression test")
    print("-" * 55)
    results = []

    # ---- the stored state is never adopted --------------------------------
    live = await _added(_sensor("v.e.temp", "16.2"), _Stored("61.16"))
    _check("the live value stays", live.native_value, 16.2, results)

    empty = await _added(_sensor("v.e.temp", ""), _Stored("61.16"))
    _check(
        "no live value: a stored DISPLAY value (°F) is not adopted as native °C",
        empty.native_value,
        None,
        results,
    )
    text = await _added(_sensor("v.e.temp", ""), _Stored("IDLE"))
    _check(
        "no live value: stored text is not adopted by a numeric sensor",
        text.native_value,
        None,
        results,
    )
    mode = await _added(_sensor("v.c.mode", "range"), _Stored("standard"))
    _check("a text sensor keeps its live text", mode.native_value, "range", results)

    # ---- attributes are still restored, as before --------------------------
    kept = await _added(
        _sensor("v.e.temp", "16.2"),
        _Stored("61.16", {"max_seen": 31.5, "unit_of_measurement": "°F"}),
    )
    _check(
        "stored attributes are restored",
        kept.extra_state_attributes.get("max_seen"),
        31.5,
        results,
    )
    _check(
        "... but not the ones that belong to the metric definition",
        "unit_of_measurement" in kept.extra_state_attributes,
        False,
        results,
    )

    # ---- nothing unstorable is handed to Home Assistant --------------------
    _check(
        "OVMSSensor does not store its native value (no RestoreSensor)",
        issubclass(OVMSSensor, RestoreSensor),
        False,
        results,
    )
    for metric in ("m.net.mdm.iccid", "xks.some.serial", "v.p.odometer"):
        sensor = _sensor(metric, ICCID)
        extra = sensor.extra_restore_state_data
        try:
            json_bytes(
                {
                    "extra_data": extra.as_dict() if extra else None,
                    "attributes": sensor.extra_state_attributes,
                }
            )
            stored = "storable"
        except (TypeError, ValueError) as ex:
            stored = f"NOT STORABLE: {ex}"
        _check(
            f"{metric} = 20 digit number: what Home Assistant stores for it",
            (extra, stored),
            (None, "storable"),
            results,
        )
    _check(
        "the ICCID is still shown in full",
        str(_sensor("m.net.mdm.iccid", ICCID).native_value),
        ICCID,
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
