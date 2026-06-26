#!/usr/bin/env python3
"""Regression test for CommandHandler background-task cleanup.

CommandHandler starts a background ``_async_cleanup_pending_commands`` task in
__init__ but never cancelled it, so each config-entry reload leaked a task.
This test asserts the new ``async_shutdown`` cancels it (and is idempotent), and
that the command timeout default is sourced from the constant.

Run standalone:  python3 scripts/tests/test_command_handler_shutdown.py
Exits non-zero on failure.
"""

import asyncio
import inspect
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from custom_components.ovms.mqtt.command_handler import CommandHandler
from custom_components.ovms.const import CONF_VEHICLE_ID, DEFAULT_COMMAND_TIMEOUT


class _FakeHass:
    def __init__(self):
        self.data = {}


def _check(name, cond, results):
    results.append(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


async def main():
    print("OVMS CommandHandler shutdown regression test")
    print("-" * 55)
    results = []

    handler = CommandHandler(_FakeHass(), {CONF_VEHICLE_ID: "x"})
    _check(
        "cleanup task is started in __init__",
        handler._cleanup_task is not None and not handler._cleanup_task.done(),
        results,
    )

    await handler.async_shutdown()
    _check(
        "async_shutdown cancels and clears the cleanup task",
        handler._cleanup_task is None,
        results,
    )

    # idempotent (e.g. double teardown) must not raise
    await handler.async_shutdown()
    _check("async_shutdown is idempotent", True, results)

    sig = inspect.signature(CommandHandler.async_send_command)
    _check(
        "command timeout default comes from DEFAULT_COMMAND_TIMEOUT",
        sig.parameters["timeout"].default == DEFAULT_COMMAND_TIMEOUT,
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
