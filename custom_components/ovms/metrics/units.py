"""Firmware-reported metric units for the OVMS integration.

MQTT carries bare metric values, so the unit of a metric without a definition
used to be guessed from its topic name. The OVMS module knows the real unit of
every metric; this module turns its ``metrics list -n`` output into Home
Assistant units and sensor typing (see ``const.METRIC_UNITS_COMMAND``).
"""

import re
from typing import Any, Dict, Optional

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergyDistance,
    UnitOfLength,
    UnitOfPower,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTime,
)

from ..const import OVMS_UNIT_LABELS

# Attribute key that carries the firmware-reported unit from topic parsing to
# the sensor, which resolves its own typing from the topic.
ATTR_REPORTED_UNIT = "reported_unit"

# Longest label first: "12.5kWh" must match "kWh", not the shorter "Wh".
_LABELS_BY_LENGTH = sorted(OVMS_UNIT_LABELS, key=len, reverse=True)

# A unit label only counts when everything before it is a number (or a comma
# separated vector of numbers). That keeps text values which merely end in a
# label's characters ("ALARM" and "12:30PM" end in the miles label "M",
# "0x3A" in the ampere label "A") from being mistaken for a measurement.
_NUMBER = re.compile(r"^[-+]?\d+(\.\d+)?([eE][-+]?\d+)?$")

# Metric names are dotted ("v.b.soc", "xsq.12v.trickle.count"); anything else
# on a line start is shell chatter such as "Usage:" or "Unrecognised metric".
_METRIC_NAME = re.compile(r"^\w+(\.\w+)+$")


def _is_numeric(value: str) -> bool:
    """Return True for a number or a comma separated vector of numbers."""
    return all(_NUMBER.match(number) for number in value.split(","))


# Device class per unit, limited to units that identify one physical quantity
# and whose device class accepts state_class MEASUREMENT. Deliberately absent:
# "%" (SoC, load, efficiency ... all differ), energy units (ENERGY needs a
# total-type state class we cannot infer), and "°C" - the firmware prints
# temperatures and temperature *differences* with the same label, and typing a
# difference as TEMPERATURE would mis-convert it to Fahrenheit.
UNIT_DEVICE_CLASSES = {
    UnitOfLength.KILOMETERS: SensorDeviceClass.DISTANCE,
    UnitOfLength.MILES: SensorDeviceClass.DISTANCE,
    UnitOfLength.METERS: SensorDeviceClass.DISTANCE,
    UnitOfLength.FEET: SensorDeviceClass.DISTANCE,
    UnitOfPower.KILO_WATT: SensorDeviceClass.POWER,
    UnitOfPower.WATT: SensorDeviceClass.POWER,
    UnitOfElectricPotential.VOLT: SensorDeviceClass.VOLTAGE,
    UnitOfElectricCurrent.AMPERE: SensorDeviceClass.CURRENT,
    UnitOfSpeed.KILOMETERS_PER_HOUR: SensorDeviceClass.SPEED,
    UnitOfSpeed.MILES_PER_HOUR: SensorDeviceClass.SPEED,
    UnitOfSpeed.METERS_PER_SECOND: SensorDeviceClass.SPEED,
    UnitOfSpeed.FEET_PER_SECOND: SensorDeviceClass.SPEED,
    UnitOfPressure.KPA: SensorDeviceClass.PRESSURE,
    UnitOfPressure.PA: SensorDeviceClass.PRESSURE,
    UnitOfPressure.PSI: SensorDeviceClass.PRESSURE,
    UnitOfPressure.BAR: SensorDeviceClass.PRESSURE,
    UnitOfTime.SECONDS: SensorDeviceClass.DURATION,
    UnitOfTime.MINUTES: SensorDeviceClass.DURATION,
    UnitOfTime.HOURS: SensorDeviceClass.DURATION,
    UnitOfTime.DAYS: SensorDeviceClass.DURATION,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT: SensorDeviceClass.SIGNAL_STRENGTH,
    UnitOfEnergyDistance.WATT_HOUR_PER_KM: SensorDeviceClass.ENERGY_DISTANCE,
    UnitOfEnergyDistance.KILO_WATT_HOUR_PER_100_KM: SensorDeviceClass.ENERGY_DISTANCE,
    UnitOfEnergyDistance.KM_PER_KILO_WATT_HOUR: SensorDeviceClass.ENERGY_DISTANCE,
    UnitOfEnergyDistance.MILES_PER_KILO_WATT_HOUR: SensorDeviceClass.ENERGY_DISTANCE,
}


def parse_metric_units(output: str) -> Dict[str, Optional[str]]:
    """Extract metric units from the output of ``metrics list -n``.

    The firmware prints one metric per line as ``"%-40.40s %s"``: the name
    padded to 40 characters, then the value immediately followed by its unit
    label (``v.c.power    2.3kW``, vectors as ``229.5,0,0V``). Metrics without
    a value print only their name.

    Args:
        output: Raw command response from the module

    Returns:
        Mapping of metric name (dotted, e.g. "xsq.v.charge.bcb.power") to

        * its Home Assistant unit, when the value is a number (or vector of
          numbers) followed by a label known to ``OVMS_UNIT_LABELS``;
        * ``None``, when the value is text ("IDLE", "yes", a date) - the metric
          is known not to be a measurement, whatever its name suggests.

        Metrics the listing says nothing conclusive about are absent, which
        callers treat as "unknown, keep guessing": those without a value, plain
        numbers (the firmware models no unit for many real quantities), numbers
        in a unit Home Assistant has no equivalent for, and names truncated at
        40 characters (they never match a real metric).
    """
    units: Dict[str, Optional[str]] = {}
    for line in output.splitlines():
        name, _, value = line.strip().partition(" ")
        value = value.strip()
        if not value or not _METRIC_NAME.match(name):
            continue
        if _is_numeric(value):
            continue
        for label in _LABELS_BY_LENGTH:
            if value.endswith(label) and _is_numeric(value[: -len(label)]):
                if OVMS_UNIT_LABELS[label] is not None:
                    units[name] = OVMS_UNIT_LABELS[label]
                break
        else:
            units[name] = None
    return units


def describe_reported_unit(
    pattern_info: Optional[Dict[str, Any]], unit: Optional[str]
) -> Dict[str, Any]:
    """Build sensor typing for an undefined metric from what the module reported.

    Args:
        pattern_info: The generic topic pattern that matched, if any
        unit: Home Assistant unit reported by the firmware, or None when the
            module reported a text value

    Returns:
        Metric info to type the sensor with. When the topic-name guess already
        agrees with the firmware the pattern is returned untouched, so nothing
        changes for metrics that were guessed correctly. Otherwise the guess is
        discarded - its device class and icon describe a different quantity -
        and the sensor becomes a plain measurement in the reported unit, or an
        untyped text sensor ("xsq.bms.voltage.state" is "OK", not a voltage).
    """
    if unit is None:
        return {"unit": None, "device_class": None, "state_class": None}

    if pattern_info is not None and pattern_info.get("unit") == unit:
        return pattern_info

    return {
        "unit": unit,
        "device_class": UNIT_DEVICE_CLASSES.get(unit),
        "state_class": SensorStateClass.MEASUREMENT,
    }
