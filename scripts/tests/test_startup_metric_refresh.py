#!/usr/bin/env python3
"""Regression test: when a full metric publish is requested at startup.

Entities exist only once a message has arrived on their topic. The module only
re-sends a metric when its value changes, and its own full publish is 20
minutes apart, so what the broker holds decides the entity set. Asking for
everything (``METRIC_REFRESH_COMMAND``) covers two cases:

  * previously discovered entities are still unavailable after a Home
    Assistant restart (issue #261);
  * the first setup of a config entry - against a broker that holds only part
    of the module's metrics, re-adding the integration left half the entities
    uncreated and nothing ever asked for the rest (issue #275). There are no
    previously registered entities to be missing then, so that case has to be
    recognised on its own.

And it must stay quiet when an entry that already had entities has them all.

Run standalone:  python3 scripts/tests/test_startup_metric_refresh.py
Exits non-zero on failure.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from custom_components.ovms.const import METRIC_REFRESH_COMMAND
from custom_components.ovms.mqtt import OVMSMQTTClient


class _Client(OVMSMQTTClient):
    """The client with only what _async_startup_metric_refresh touches."""

    # pylint: disable=super-init-not-called
    def __init__(self, had_entities, missing):
        self._shutting_down = False
        self.connected = True
        self._startup_refresh_cancel = None
        self._entry_had_entities = had_entities
        self._missing = missing
        self.commands = []

    def _count_missing_registry_entities(self):
        return self._missing

    async def async_send_command(self, command, timeout=None, **_kwargs):
        self.commands.append(command)
        return {"success": True}


def _check(name, actual, expected, results):
    ok = actual == expected
    results.append(ok)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"        expected {expected!r}\n        actual   {actual!r}")


async def main():
    print("OVMS startup metric refresh test")
    print("-" * 55)
    results = []

    for name, had_entities, missing, expected in (
        ("first setup asks even though nothing is missing", False, 0, True),
        ("first setup asks when entities are missing too", False, 3, True),
        ("a restart with entities missing asks", True, 3, True),
        ("a restart with everything present stays quiet", True, 0, False),
    ):
        client = _Client(had_entities, missing)
        await client._async_startup_metric_refresh(None)
        _check(name, client.commands == [METRIC_REFRESH_COMMAND], expected, results)

    # Guards that must come before the decision.
    for name, attribute in (
        ("nothing is sent while shutting down", "_shutting_down"),
        ("nothing is sent while disconnected", "connected"),
    ):
        client = _Client(False, 0)
        setattr(client, attribute, attribute == "_shutting_down")
        await client._async_startup_metric_refresh(None)
        _check(name, client.commands, [], results)

    print("-" * 55)
    if all(results):
        print(f"All {len(results)} checks passed.")
        return 0
    print(f"{results.count(False)} of {len(results)} checks FAILED.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
