#!/usr/bin/env python3
"""Regression test: config-flow MQTT probing must not block the event loop.

`test_mqtt_connection` used to call `socket.gethostbyname()` and open a probe
socket (`socket.connect_ex`) directly on the asyncio event loop. Home Assistant
2024+ flags such blocking I/O ("Detected blocking call ... inside the event
loop") and it can stall the whole instance while the OS resolver/connect times
out on an unreachable host.

This test drives the REAL `test_mqtt_connection` through a fake hass whose
`async_add_executor_job` records every offloaded call and runs it in a real
thread pool. It asserts that DNS resolution and the TCP port probe are both
dispatched to the executor (not the loop), that the function still returns the
correct `cannot_connect` result for a closed port, and that the standalone
`_probe_tcp_port` helper reports open/closed ports correctly.

Run standalone:  python3 scripts/tests/test_config_flow_blocking.py
Exits non-zero on failure.
"""

import asyncio
import os
import socket
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from homeassistant.const import CONF_HOST, CONF_PORT, CONF_PROTOCOL

from custom_components.ovms.config_flow.mqtt_connection import (
    test_mqtt_connection,
    _probe_tcp_port,
)
from custom_components.ovms.const import ERROR_CANNOT_CONNECT


class _FakeHass:
    """Minimal hass stub that runs executor jobs in a real thread pool."""

    def __init__(self):
        self._pool = ThreadPoolExecutor(max_workers=4)
        self.executor_calls = []

    async def async_add_executor_job(self, func, *args):
        self.executor_calls.append(getattr(func, "__name__", repr(func)))
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._pool, func, *args)


def _free_closed_port() -> int:
    """Reserve an ephemeral port then release it so it is closed."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _check(name, cond, results):
    results.append(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


async def main():
    print("OVMS config-flow non-blocking probe regression test")
    print("-" * 55)
    results = []

    # ---- _probe_tcp_port reports open/closed correctly ----
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    open_port = listener.getsockname()[1]
    _check(
        "probe reports an open port as open",
        _probe_tcp_port("127.0.0.1", open_port, 2) is True,
        results,
    )
    listener.close()

    closed_port = _free_closed_port()
    _check(
        "probe reports a closed port as closed",
        _probe_tcp_port("127.0.0.1", closed_port, 1) is False,
        results,
    )

    # ---- test_mqtt_connection offloads blocking I/O and still works ----
    hass = _FakeHass()
    config = {
        CONF_HOST: "127.0.0.1",
        CONF_PORT: closed_port,
        CONF_PROTOCOL: "mqtt",  # plain TCP, no TLS/ws
    }
    result = await test_mqtt_connection(hass, config)

    _check(
        "closed port -> success is False",
        result.get("success") is False,
        results,
    )
    _check(
        "closed port -> error_type is cannot_connect",
        result.get("error_type") == ERROR_CANNOT_CONNECT,
        results,
    )
    _check(
        "DNS resolution was offloaded to the executor",
        "gethostbyname" in hass.executor_calls,
        results,
    )
    _check(
        "TCP port probe was offloaded to the executor",
        "_probe_tcp_port" in hass.executor_calls,
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
