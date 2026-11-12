#!/usr/bin/env python3
"""Regression test for topic-blacklist de-duplication in the options flow.

A conversion of the blacklist string into a list *without* de-duplicating once
ran before the dedicated de-dup block, whose ``isinstance(..., str)`` guard then
saw a list, so duplicate patterns were stored verbatim.

This drives the REAL ``OVMSOptionsFlow.async_step_init`` with a blacklist
containing duplicates, and asserts the saved blacklist is de-duplicated.

Run standalone:  python3 scripts/tests/test_options_blacklist_dedup.py
Exits non-zero on failure.
"""

# pylint: disable=duplicate-code

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from custom_components.ovms.config_flow.options_flow import OVMSOptionsFlow
from custom_components.ovms.const import CONF_TOPIC_BLACKLIST


class _FakeEntry:
    """Minimal config-entry stand-in, its port unchanged by the submit."""

    entry_id = "test_entry"
    data = {}
    options = {}


class _Flow(OVMSOptionsFlow):
    """The options flow with its entry at hand, as Home Assistant provides it."""

    config_entry = _FakeEntry()


def _check(name, cond, results):
    results.append(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


async def main():
    print("OVMS options-flow blacklist de-dup regression test")
    print("-" * 55)
    results = []

    flow = _Flow(_FakeEntry())
    captured = {}
    # Capture what async_step_init would persist instead of creating a real entry.
    flow.async_create_entry = lambda **kw: captured.update(kw) or kw

    await flow.async_step_init({CONF_TOPIC_BLACKLIST: "log, log, xyz ,xyz,, log"})
    stored = captured.get("data", {}).get(CONF_TOPIC_BLACKLIST)

    _check("blacklist is stored as a list", isinstance(stored, list), results)
    _check(
        f"duplicates removed, order preserved (got {stored!r})",
        stored == ["log", "xyz"],
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
