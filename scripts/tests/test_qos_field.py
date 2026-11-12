#!/usr/bin/env python3
"""Regression test: the setup and options forms show the QoS level selected.

With numeric options the frontend left every QoS radio button unmarked, the
default included. This checks the field as Home Assistant serializes it for the
frontend, and that the selected level is still stored as an int.

Run standalone:  python3 scripts/tests/test_qos_field.py
Exits non-zero on failure.
"""

# pylint: disable=wrong-import-position

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Home Assistant installs its voluptuous shim on import, before anything uses it.
import homeassistant  # noqa: F401  # pylint: disable=unused-import
import probatio
from homeassistant.const import CONF_HOST
from homeassistant.helpers import config_validation as cv

from custom_components.ovms.config_flow import OVMSConfigFlow
from custom_components.ovms.config_flow.options_flow import OVMSOptionsFlow
from custom_components.ovms.const import CONF_QOS, DEFAULT_QOS

STORED_QOS = 0


class _FakeEntry:
    """Minimal config-entry stand-in with a QoS other than the default."""

    entry_id = "test_entry"
    data = {CONF_QOS: STORED_QOS}
    options = {}


class _Flow(OVMSOptionsFlow):
    """The options flow with its entry at hand, as Home Assistant provides it."""

    config_entry = _FakeEntry()


def _selected(form):
    """Return the QoS option the frontend shows selected, or None."""
    fields = probatio.to_field_list(
        form["data_schema"], custom_serializer=cv.custom_serializer
    )
    field = next(field for field in fields if field["name"] == CONF_QOS)
    options = field.get("selector", {}).get("select", {}).get("options", [])
    return field["default"] if field["default"] in options else None


def _check(name, cond, results):
    results.append(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


async def main():
    print("OVMS QoS field regression test")
    print("-" * 55)
    results = []

    setup = await OVMSConfigFlow().async_step_user()
    _check(
        "setup form shows the default QoS selected",
        _selected(setup) == str(DEFAULT_QOS),
        results,
    )
    stored = setup["data_schema"]({CONF_HOST: "broker"})[CONF_QOS]
    _check(
        f"the selected level is stored as an int (got {stored!r})",
        stored == DEFAULT_QOS and isinstance(stored, int),
        results,
    )

    options = await _Flow(_FakeEntry()).async_step_init()
    _check(
        "options form shows the entry's QoS selected",
        _selected(options) == str(STORED_QOS),
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
