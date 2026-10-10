#!/usr/bin/env python3
"""Regression test: OVMS timestamps keep the module's time zone (issue #277).

Server V3 publishes a date/time metric as text in the metric's native unit: a
``DateUTC`` metric as ``"%F %T UTC"``, a ``DateLocal`` metric as ``"%F %T %Z"``
in the MODULE's zone. The parser dropped the zone token and stamped Home
Assistant's offset onto the wall clock, so a module on the firmware default
(UTC) was off by the full offset - 13 h on Pacific/Auckland.

It also returned ``dt_util.now()`` for anything it could not parse, which made
the three metrics that are not points in time (``v.c.timerstart``,
``v.g.timerstart`` - firmware unit TimeUTC, "HH:MM:SS" - and ``xmg.v.bms.time``
- a plain string) display the current clock.

Run standalone:  python3 scripts/tests/test_timestamp_parsing.py
Exits non-zero on failure.
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, available_timezones

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.util import dt as dt_util

from custom_components.ovms.const import MODULE_TIMEZONE_COMMAND
from custom_components.ovms.metrics import METRIC_DEFINITIONS
from custom_components.ovms.sensor.entities import (
    NON_RESTORABLE_ATTRIBUTES,
    format_sensor_value,
)
from custom_components.ovms.module_time_zone import (
    _standard_offset,
    get_module_time_zone,
)
from custom_components.ovms.sensor.parsers import parse_value

AUCKLAND = "Pacific/Auckland"


def _check(name, actual, expected, results):
    ok = actual == expected
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        expected {expected!r}\n        actual   {actual!r}")


def _parse(payload):
    return parse_value(payload, SensorDeviceClass.TIMESTAMP, None, False)


def main():
    print("OVMS timestamp parsing test")
    print("-" * 55)
    results = []

    dt_util.set_default_time_zone(dt_util.get_time_zone(AUCKLAND))

    # A UTC payload is the same instant whatever Home Assistant's zone is.
    _check(
        "DateUTC payload keeps UTC",
        _parse("2026-10-03 11:28:28 UTC"),
        datetime(2026, 10, 3, 11, 28, 28, tzinfo=timezone.utc),
        results,
    )
    _check(
        "zone token is case insensitive",
        _parse("2026-10-03 11:28:28 utc"),
        datetime(2026, 10, 3, 11, 28, 28, tzinfo=timezone.utc),
        results,
    )
    # A module zone that is not UTC can only be an abbreviation, so it is read
    # as Home Assistant's zone - correct when the two match, as the README asks.
    _check(
        "DateLocal payload is read in Home Assistant's zone",
        _parse("2026-10-04 00:28:28 NZDT"),
        datetime(2026, 10, 4, 0, 28, 28, tzinfo=timezone(timedelta(hours=13))),
        results,
    )
    _check(
        "payload without a zone is read in Home Assistant's zone",
        _parse("2026-10-04 00:28:28"),
        datetime(2026, 10, 4, 0, 28, 28, tzinfo=timezone(timedelta(hours=13))),
        results,
    )
    _check(
        "ISO payload with an offset is honoured",
        _parse("2026-10-03T11:28:28+00:00"),
        datetime(2026, 10, 3, 11, 28, 28, tzinfo=timezone.utc),
        results,
    )
    for payload in ("07:30:00", "03/10/26 11:28:28", "", "not a time"):
        _check(f"unparseable {payload!r} is unknown", _parse(payload), None, results)

    # The displayed state is the wall clock in Home Assistant's zone, with no
    # offset left behind - splitting the ISO string on "+" kept it west of
    # Greenwich ("2026-10-03 at 11:28:28-04:00").
    for offset in (13, 0, -4):
        value = datetime(
            2026, 10, 3, 11, 28, 28, tzinfo=timezone(timedelta(hours=offset))
        )
        _check(
            f"display at UTC{offset:+d} has no offset",
            format_sensor_value(value, SensorDeviceClass.TIMESTAMP, {}),
            "2026-10-03 at 11:28:28",
            results,
        )
    _check(
        "a UTC payload displays as Home Assistant local time",
        format_sensor_value(
            _parse("2026-10-03 11:28:28 UTC"), SensorDeviceClass.TIMESTAMP, {}
        ),
        "2026-10-04 at 00:28:28",
        results,
    )

    # The metrics that are not points in time must not be typed as timestamps.
    for metric in ("v.c.timerstart", "v.g.timerstart", "xmg.v.bms.time"):
        _check(
            f"{metric} is not a timestamp sensor",
            METRIC_DEFINITIONS[metric].get("device_class"),
            None,
            results,
        )
    _check(
        "m.time.utc stays a timestamp sensor",
        METRIC_DEFINITIONS["m.time.utc"]["device_class"],
        SensorDeviceClass.TIMESTAMP,
        results,
    )

    # The demotions only take effect if the stored device class is not restored.
    _check(
        "original_device_class is never restored",
        "original_device_class" in NON_RESTORABLE_ATTRIBUTES,
        True,
        results,
    )

    # The module is put on Home Assistant's zone, which needs a POSIX TZ string
    # (it goes straight to setenv("TZ")), not the IANA name.
    for zone, posix in (
        (AUCKLAND, "NZST-12NZDT,M9.5.0,M4.1.0/3"),
        ("Europe/Stockholm", "CET-1CEST,M3.5.0,M10.5.0/3"),
        ("America/New_York", "EST5EDT,M3.2.0,M11.1.0"),
        ("Asia/Kolkata", "IST-5:30"),
        ("UTC", "UTC0"),
        # tzdata names this zone numerically, which the module cannot read.
        ("America/Bogota", None),
        ("Not/AZone", None),
        (None, None),
    ):
        _check(
            f"POSIX time zone for {zone}", get_module_time_zone(zone), posix, results
        )
    # "config set" takes exactly 3 arguments, so the POSIX string has to stay a
    # single shell token: "config set vehicle timezone <tz>".
    _check(
        "the module command is one shell token per argument",
        MODULE_TIMEZONE_COMMAND.format(timezone=get_module_time_zone(AUCKLAND)).split(),
        ["config", "set", "vehicle", "timezone", "NZST-12NZDT,M9.5.0,M4.1.0/3"],
        results,
    )

    # Every zone on the machine, not just the ones above: nothing the module
    # would misread may be sent, and what is sent has to match the zone.
    sent = {
        zone: posix
        for zone in available_timezones()
        if (posix := get_module_time_zone(zone))
    }
    _check(
        "no zone yields a string the module would misread",
        [z for z, p in sent.items() if "<" in p or "/-" in p],
        [],
        results,
    )
    _check(
        "every string sent has the zone's standard offset",
        [
            zone
            for zone, posix in sent.items()
            if _standard_offset(posix)
            != -(
                datetime.now(ZoneInfo(zone)).utcoffset()
                - datetime.now(ZoneInfo(zone)).dst()
            )
        ],
        [],
        results,
    )
    _check(
        "most zones are still covered",
        len(sent) > len(available_timezones()) // 2,
        True,
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
