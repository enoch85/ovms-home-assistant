#!/usr/bin/env python3
"""Regression test for firmware-reported metric units.

MQTT carries bare metric values, so the unit of a metric without a definition
used to be guessed from its topic name - and the guess is often wrong (every
"*.power" was assumed to be W while OVMS registers most power metrics in kW,
"v.c.duration.range" was read as kilometres). The module can describe itself:
``metrics list -n`` prints every metric with its native unit label.

This drives the REAL parser and the REAL topic parser / sensor pipeline and
checks that:
  * the firmware output format is parsed precisely (and text is never mistaken
    for a measurement),
  * a reported unit overrules a wrong topic-name guess,
  * a correct guess is left completely untouched,
  * a metric DEFINITION is never overruled,
  * nothing changes when the module reports nothing (old firmware / offline).

Run standalone:  python3 scripts/tests/test_firmware_reported_units.py
Exits non-zero on failure.
"""

import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
logging.disable(logging.CRITICAL)

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.components.sensor.const import (
    DEVICE_CLASS_STATE_CLASSES,
    DEVICE_CLASS_UNITS,
)

from custom_components.ovms.attribute_manager import AttributeManager
from custom_components.ovms.const import METRIC_UNITS_COMMAND, OVMS_UNIT_LABELS
from custom_components.ovms.metrics.patterns import TOPIC_PATTERNS
from custom_components.ovms.metrics.units import (
    ATTR_REPORTED_UNIT,
    UNIT_DEVICE_CLASSES,
    describe_reported_unit,
    parse_metric_units,
)
from custom_components.ovms.mqtt.entity_registry import EntityRegistry
from custom_components.ovms.mqtt.topic_parser import TopicParser
from custom_components.ovms.naming_service import EntityNamingService
from custom_components.ovms.sensor.entities import OVMSSensor

CONFIG = {
    "topic_prefix": "ovms",
    "mqtt_username": "u",
    "vehicle_id": "car",
    "topic_structure": "{prefix}/{mqtt_username}/{vehicle_id}",
}


def _line(name, value=""):
    """Format one line exactly like the firmware: printf("%-40.40s %s\\n")."""
    return f"{name:<40.40s} {value}" if value else name


# A realistic slice of `metrics list -n` output.
SAMPLE = "\n".join(
    [
        _line("m.net.sq", "-85dBm"),
        _line("m.version", "3.3.006-112-g0712b636/ota_1/edge (build idf v3.3.4)"),
        _line("v.b.12v.voltage", "12.61V"),
        _line("v.b.consumption", "165.2Wh/km"),
        _line("v.b.energy.used", "4.1kWh"),
        _line("v.b.power", "2.3kW"),
        _line("v.b.soc", "81.2%"),
        _line("v.b.temp", "21°C"),
        _line("v.c.charging", "no"),
        _line("v.c.duration.full", "95Min"),
        _line("v.c.kwh.grid"),  # defined metric without a value: name only
        _line("v.e.parktime", "86400Sec"),
        _line("v.p.direction", "271.5°"),
        _line("v.p.gpstime", "2026-09-20 10:11:12 CEST"),
        _line("v.p.odometer", "48211.3km"),
        _line("v.p.speed", "0km/h"),
        _line("v.t.pressure", "230,231,229,232kPa"),
        _line("xsq.bms.ev.mode", "ALARM"),  # text ending in the miles label "M"
        _line("xsq.ddt4all.canbyte", "0x3A"),  # text ending in the ampere label
        _line("xsq.obl.volts", "229.5,0,0V"),
        _line("xsq.v.bat.consumption.best", "11.2kWh/100km"),
        _line("xsq.v.charge.bcb.power", "2300W"),
        _line("xsq.v.start.time", "12:30PM"),
        _line("xsq.adc.factor", "195.2"),  # numeric but unit-less ("Other")
        _line("m.net.good.sq", "20sq"),  # label with no Home Assistant unit
        _line("xvu.a.very.long.metric.name.that.exceeds.forty.chars", "5km"),
        "Unrecognised metric name",
        "",
    ]
)


def _check(name, got, want, results):
    ok = got == want
    results.append(ok)
    print(
        f"  {'PASS' if ok else 'FAIL'}  {name}: {got!r}"
        + ("" if ok else f" != {want!r}")
    )


def _sensor(metric, payload, reported_units=None):
    """Build the sensor for a metric through the real pipeline."""
    parser = TopicParser(CONFIG, EntityRegistry())
    parser.reported_units = reported_units or {}
    topic = "ovms/u/car/metric/" + metric.replace(".", "/")
    parsed = parser.parse_topic(topic, payload)
    friendly = EntityNamingService(CONFIG).create_friendly_name(
        parsed["parts"],
        parsed["metric_info"],
        topic,
        parsed["raw_name"],
        parsed["metric_defined"],
    )
    attributes = AttributeManager(CONFIG).prepare_attributes(
        topic, "x", parsed["parts"], parsed["metric_info"]
    )
    return parsed, OVMSSensor(
        "uid", parsed["name"], topic, payload, {}, attributes, friendly
    )


def main():
    print("OVMS firmware-reported metric units regression test")
    print("-" * 55)
    results = []

    _check(
        "the command asks for NATIVE units",
        METRIC_UNITS_COMMAND,
        "metrics list -n",
        results,
    )

    # ---- 1) parsing the firmware output ---------------------------------
    units = parse_metric_units(SAMPLE)
    expected = {
        "m.net.sq": "dBm",
        "v.b.12v.voltage": "V",
        "v.b.consumption": "Wh/km",
        "v.b.energy.used": "kWh",  # longest label wins: not "Wh"
        "v.b.power": "kW",  # ... and not "W"
        "v.b.soc": "%",
        "v.b.temp": "°C",  # ... and not "°"
        "v.c.duration.full": "min",
        "v.e.parktime": "s",
        "v.p.direction": "°",
        "v.p.odometer": "km",
        "v.p.speed": "km/h",
        "v.t.pressure": "kPa",  # vectors carry one trailing label
        "xsq.obl.volts": "V",
        "xsq.v.bat.consumption.best": "kWh/100km",
        "xsq.v.charge.bcb.power": "W",
        # the firmware truncates names at 40 characters; harmless, never matches
        "xvu.a.very.long.metric.name.that.exceeds": "km",
        # text values: known NOT to be measurements, whatever the name suggests
        "m.version": None,
        "v.c.charging": None,
        "v.p.gpstime": None,
        "xsq.bms.ev.mode": None,  # "ALARM" ends in the miles label "M"
        "xsq.ddt4all.canbyte": None,  # "0x3A" ends in the ampere label "A"
        "xsq.v.start.time": None,  # "12:30PM"
    }
    _check("units parsed from `metrics list -n` output", units, expected, results)
    # Nothing conclusive: no value, a bare number (the firmware models no unit
    # for many real quantities), or a number in a unit without an equivalent.
    for absent in ("v.c.kwh.grid", "xsq.adc.factor", "m.net.good.sq"):
        _check(f"{absent} stays unknown", absent in units, False, results)
    _check(
        "an error reply yields nothing",
        parse_metric_units("Usage: metrics list [-cpst]"),
        {},
        results,
    )
    _check("an empty reply yields nothing", parse_metric_units(""), {}, results)

    # ---- 2) the typing rule ---------------------------------------------
    power = TOPIC_PATTERNS["power"]
    _check(
        "a correct guess is returned untouched (same object)",
        describe_reported_unit(power, "W") is power,
        True,
        results,
    )
    typed = describe_reported_unit(power, "kW")
    _check(
        "a wrong guess is replaced by the reported unit", typed["unit"], "kW", results
    )
    _check(
        "... typed as POWER", typed["device_class"], SensorDeviceClass.POWER, results
    )
    _check(
        "... and drops the guess's icon/name",
        sorted(typed),
        ["device_class", "state_class", "unit"],
        results,
    )
    _check(
        "no pattern at all still gets typed",
        describe_reported_unit(None, "km")["device_class"],
        SensorDeviceClass.DISTANCE,
        results,
    )
    _check(
        "'%' gets no device class (SoC, load, efficiency differ)",
        describe_reported_unit(None, "%")["device_class"],
        None,
        results,
    )
    _check(
        "'°C' gets no device class (could be a temperature difference)",
        describe_reported_unit(None, "°C")["device_class"],
        None,
        results,
    )

    invalid = [
        (unit, dc)
        for unit, dc in UNIT_DEVICE_CLASSES.items()
        if unit not in DEVICE_CLASS_UNITS[dc]
        or SensorStateClass.MEASUREMENT not in DEVICE_CLASS_STATE_CLASSES[dc]
    ]
    _check(
        "every unit/device-class pair is valid in Home Assistant with MEASUREMENT",
        invalid,
        [],
        results,
    )
    _check(
        "every typed unit is one the firmware can report",
        [u for u in UNIT_DEVICE_CLASSES if u not in OVMS_UNIT_LABELS.values()],
        [],
        results,
    )

    # ---- 3) the real pipeline -------------------------------------------
    # An unsupported vehicle ("xks" has no module here): pure topic-name guess.
    _, guessed = _sensor("xks.b.pack.power", "42.5")
    _check(
        "without a report the guess stands (W) - unchanged behaviour",
        guessed.native_unit_of_measurement,
        "W",
        results,
    )

    parsed, told = _sensor("xks.b.pack.power", "42.5", {"xks.b.pack.power": "kW"})
    _check(
        "a reported unit overrules the wrong guess",
        told.native_unit_of_measurement,
        "kW",
        results,
    )
    _check(
        "... keeps a valid device class",
        told.device_class,
        SensorDeviceClass.POWER,
        results,
    )
    _check("... and the value", told.native_value, 42.5, results)
    _check(
        "the wiring key is not a user-facing attribute",
        ATTR_REPORTED_UNIT in told.extra_state_attributes,
        False,
        results,
    )
    _check(
        "the metric is flagged as undefined", parsed["metric_defined"], False, results
    )

    _, duration = _sensor("xks.c.duration.range", "95", {"xks.c.duration.range": "min"})
    _check(
        "'*.duration.range' is a duration in minutes, not a range in km",
        duration.extra_state_attributes.get("original_unit"),
        "min",
        results,
    )

    _, plain = _sensor("xks.e.cabin.humidity", "40", {"xks.e.cabin.humidity": "%"})
    _check(
        "a metric no pattern matches gets its reported unit",
        plain.native_unit_of_measurement,
        "%",
        results,
    )
    _check(
        "... as a measurement", plain.state_class, SensorStateClass.MEASUREMENT, results
    )

    _, agreed = _sensor("xks.b.pack.voltage", "355.2", {"xks.b.pack.voltage": "V"})
    _check(
        "a correct guess keeps its pattern icon",
        agreed.icon,
        TOPIC_PATTERNS["voltage"]["icon"],
        results,
    )

    # A DEFINITION is authoritative - also when the module disagrees.
    parsed, defined = _sensor("v.b.power", "2.3", {"v.b.power": "W"})
    _check(
        "a defined metric is flagged as defined",
        parsed["metric_defined"],
        True,
        results,
    )
    _check(
        "a definition is never overruled",
        defined.native_unit_of_measurement,
        "kW",
        results,
    )
    _check(
        "... and carries no reported unit",
        ATTR_REPORTED_UNIT in (parsed["metric_info"] or {}),
        False,
        results,
    )

    # A text value overrules a numeric guess taken from the metric's NAME.
    _, guessed_text = _sensor("xks.b.voltage.state", "OK")
    _check(
        "without a report a text metric named '*voltage*' is a broken voltage sensor",
        (guessed_text.native_value, guessed_text.native_unit_of_measurement),
        (None, "V"),
        results,
    )
    _, told_text = _sensor("xks.b.voltage.state", "OK", {"xks.b.voltage.state": None})
    _check(
        "reported as text it shows its value, untyped",
        (
            told_text.native_value,
            told_text.native_unit_of_measurement,
            told_text.device_class,
            told_text.state_class,
        ),
        ("OK", None, None, None),
        results,
    )

    # Binary sensors have no unit: they must not pick one up.
    parser = TopicParser(CONFIG, EntityRegistry())
    parser.reported_units = {"v.c.charging": "A"}
    charging = parser.parse_topic("ovms/u/car/metric/v/c/charging", "no")
    _check(
        "non-sensor entities ignore reported units",
        ATTR_REPORTED_UNIT in (charging["metric_info"] or {}),
        False,
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
