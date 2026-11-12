#!/usr/bin/env python3
"""Regression test: the setup and options forms show the QoS level selected."""

# pylint: disable=wrong-import-position

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import homeassistant  # noqa: F401  # pylint: disable=unused-import
import probatio
from homeassistant.const import CONF_HOST
from homeassistant.helpers import config_validation as cv

from custom_components.ovms.config_flow import OVMSConfigFlow
from custom_components.ovms.config_flow.options_flow import OVMSOptionsFlow
from custom_components.ovms.const import CONF_QOS


class _Entry:
    entry_id = "test_entry"
    data = {CONF_QOS: 0}
    options = {}


class _Flow(OVMSOptionsFlow):
    config_entry = _Entry()


def _marked(form):
    """Return the QoS option the frontend marks: the default, if it is an option."""
    fields = probatio.to_field_list(
        form["data_schema"], custom_serializer=cv.custom_serializer
    )
    field = next(field for field in fields if field["name"] == CONF_QOS)
    options = field["selector"]["select"]["options"]
    return field["default"] if field["default"] in options else None


async def main():
    setup = await OVMSConfigFlow().async_step_user()
    options = await _Flow(_Entry()).async_step_init()
    stored = setup["data_schema"]({CONF_HOST: "h"})[CONF_QOS]
    checks = {
        "setup form marks QoS 1": _marked(setup) == "1",
        "options form marks the entry's QoS": _marked(options) == "0",
        "QoS is stored as an int": stored == 1,
    }
    for name, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
