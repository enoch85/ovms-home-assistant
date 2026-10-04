"""The time zone string an OVMS module can be given.

The module feeds its ``vehicle timezone`` config value straight to
``setenv("TZ")`` and ``tzset()`` (main/ovms_time.cpp), so it has to be a POSIX
TZ string its own libc understands. That libc is newlib as built for the ESP32
toolchain OVMS uses, and it reads less than the one tzdata writes for, so a
string is only handed over once it has been checked against what newlib does
and against the zone it came from.
"""

import os
import zoneinfo
from datetime import datetime, timedelta, timezone
from importlib import resources
from typing import Optional

from .const import (
    MODULE_TIME_ZONE_DIGITS,
    MODULE_TIME_ZONE_REJECTED,
    MODULE_TIME_ZONE_SAMPLE_DAYS,
    MODULE_TIME_ZONE_SAMPLE_STEP_DAYS,
    MODULE_TIME_ZONE_SUMMER_TIME_MARKER,
)


def _read_tzif_footer(time_zone: str) -> Optional[str]:
    """Return the POSIX TZ string a zone's TZif file ends with.

    Every TZif v2+ file ends with "\\n<POSIX TZ string>\\n"; zoneinfo reads the
    file but exposes no accessor for that line.
    """
    data = None
    for directory in zoneinfo.TZPATH:
        try:
            with open(os.path.join(directory, time_zone), "rb") as tz_file:
                data = tz_file.read()
            break
        except OSError:
            continue
    if data is None:
        try:
            package, _, name = ("tzdata.zoneinfo/" + time_zone).rpartition("/")
            data = (
                resources.files(package.replace("/", ".")).joinpath(name).read_bytes()
            )
        except (ImportError, OSError):
            return None

    if not data.startswith(b"TZif") or data[4:5] == b"\x00":  # v1: no footer
        return None
    footer = data[data.rfind(b"\n", 0, len(data) - 1) + 1 : -1]
    return footer.decode("ascii", "ignore") or None


def _standard_offset(posix_time_zone: str) -> Optional[timedelta]:
    """Return the standard offset a POSIX TZ string opens with, west positive.

    Only the leading "<name><offset>" is read: the zone name, then an optional
    sign and up to three colon-separated numbers.
    """
    position = 0
    while (
        position < len(posix_time_zone)
        and posix_time_zone[position] not in MODULE_TIME_ZONE_DIGITS + "+-"
    ):
        position += 1
    if position == 0:
        return None

    negative = posix_time_zone[position] == "-"
    if posix_time_zone[position] in "+-":
        position += 1

    fields = []
    while len(fields) < 3:
        start = position
        while (
            position < len(posix_time_zone)
            and posix_time_zone[position] in MODULE_TIME_ZONE_DIGITS
        ):
            position += 1
        if position == start:
            return None
        fields.append(int(posix_time_zone[start:position]))
        if posix_time_zone[position : position + 1] != ":":
            break
        position += 1

    fields += [0] * (3 - len(fields))
    offset = timedelta(hours=fields[0], minutes=fields[1], seconds=fields[2])
    return -offset if negative else offset


def _describes_zone(posix_time_zone: str, zone_name: str) -> bool:
    """Check a POSIX TZ string against the zone it is supposed to describe.

    A TZif footer is not always in step with the rest of its own file - tzdata
    2026b ships America/Vancouver as "MST7" where the zone really is PST8PDT -
    and sending that would move the module an hour off and drop its summer
    time. Comparing the standard offset and whether summer time exists at all
    catches that without a second POSIX implementation.
    """
    standard = _standard_offset(posix_time_zone)
    if standard is None:
        return False

    zone = zoneinfo.ZoneInfo(zone_name)
    now = datetime.now(timezone.utc)
    samples = [
        (now + timedelta(days=days)).astimezone(zone)
        for days in range(
            0, MODULE_TIME_ZONE_SAMPLE_DAYS, MODULE_TIME_ZONE_SAMPLE_STEP_DAYS
        )
    ]
    # POSIX counts west of Greenwich as positive, Python counts it as negative.
    offsets = {-(sample.utcoffset() - sample.dst()) for sample in samples}
    has_summer_time = MODULE_TIME_ZONE_SUMMER_TIME_MARKER in posix_time_zone
    return offsets == {standard} and any(sample.dst() for sample in samples) == (
        has_summer_time
    )


def get_module_time_zone(time_zone: Optional[str]) -> Optional[str]:
    """Return the POSIX TZ string to give the module for a Home Assistant zone.

    Args:
        time_zone: IANA name, e.g. Home Assistant's "Pacific/Auckland".

    Returns:
        The POSIX TZ string, e.g. "NZST-12NZDT,M9.5.0,M4.1.0/3", or None when
        the module could not use it. Never a string the module would misread.

    Notes:
        Reads a file; call from an executor.
    """
    if not time_zone:
        return None
    try:
        posix_time_zone = _read_tzif_footer(time_zone)
    except ValueError:  # not a zone name at all
        return None
    if not posix_time_zone:
        return None
    if any(rejected in posix_time_zone for rejected in MODULE_TIME_ZONE_REJECTED):
        return None
    try:
        return posix_time_zone if _describes_zone(posix_time_zone, time_zone) else None
    except zoneinfo.ZoneInfoNotFoundError:
        return None
