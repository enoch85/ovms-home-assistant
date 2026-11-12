#!/usr/bin/env python3
"""Broker port and protocol detection (issue #281), and the options form using it."""

# pylint: disable=wrong-import-position,protected-access

import asyncio
import os
import socket
import ssl
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Home Assistant installs its voluptuous shim on import, before anything uses it.
import homeassistant  # noqa: F401  # pylint: disable=unused-import
import paho.mqtt.client as mqtt

from custom_components.ovms.config_flow import mqtt_connection, options_flow
from custom_components.ovms.const import (
    CONF_HOST,
    CONF_LOCK_PIN,
    CONF_PORT,
    CONF_PROTOCOL,
    CONF_VERIFY_SSL,
    ERROR_CANNOT_CONNECT,
    ERROR_TLS_ERROR,
    VERIFY_SSL_FIELD,
)

REFUSED = {"success": False, "error_type": ERROR_CANNOT_CONNECT}


class _Hass:
    """Runs executor jobs inline."""

    async def async_add_executor_job(self, func, *args):
        return func(*args)


class _Entry:
    """Config entry stand-in for the options flow."""

    entry_id = "test_entry"
    options = {}

    def __init__(self, data):
        self.data = data


async def _detect(config, open_ports=(), answers=None):
    """Detect with fake ports and connection tests; return (result, tries)."""
    tries = []

    async def connection_test(_hass, tried):
        tries.append((tried[CONF_PORT], tried[CONF_PROTOCOL], tried[CONF_VERIFY_SSL]))
        return (answers or {}).get(tried[CONF_PROTOCOL], REFUSED)

    mqtt_connection._probe_tcp_port = lambda _host, port, _timeout: port in open_ports
    mqtt_connection.test_mqtt_connection = connection_test
    return await mqtt_connection.async_detect_broker(_Hass(), config), tries


async def _options_submit(stored, user_input, found=None):
    """Submit the options form; return (saved data or None, form, detections)."""
    detections = []

    async def detect(_hass, config):
        detections.append(config.get(CONF_PORT))
        if found:
            config[CONF_PORT], config[CONF_PROTOCOL] = found
        return {"success": bool(found)}

    class _Flow(options_flow.OVMSOptionsFlow):
        config_entry = _Entry(stored)

    options_flow.async_detect_broker = detect
    flow = _Flow(_Flow.config_entry)
    saved, shown = {}, {}
    flow.async_create_entry = lambda **kw: saved.update(kw) or kw
    flow.async_show_form = lambda **kw: shown.update(kw) or kw
    await flow.async_step_init(dict(user_input))
    return saved.get("data"), shown, detections


async def main():
    checks = {}

    # The real connection test, with a listening port and an untrusted certificate.
    with socket.create_server(("127.0.0.1", 0)) as listener:

        def untrusted(*_args, **_kwargs):
            raise ssl.SSLCertVerificationError(1, "certificate verify failed")

        mqtt.Client.connect = untrusted
        result = await mqtt_connection.test_mqtt_connection(
            _Hass(),
            {
                CONF_HOST: "127.0.0.1",
                CONF_PORT: listener.getsockname()[1],
                CONF_PROTOCOL: "mqtts",
                CONF_VERIFY_SSL: True,
            },
        )
    checks["an untrusted certificate is a TLS error"] = (
        result["error_type"] == ERROR_TLS_ERROR
    )

    _, tries = await _detect(
        {CONF_HOST: "h", CONF_VERIFY_SSL: True}, open_ports=(1883, 8083)
    )
    checks["no port: the first open standard port, with its protocol"] = tries == [
        (1883, "mqtt", False)
    ]
    _, tries = await _detect(
        {CONF_HOST: "h", CONF_PORT: 1884}, answers={"ws": {"success": True}}
    )
    checks["an entered port: each protocol until one connects"] = [
        protocol for _, protocol, _ in tries
    ] == ["wss", "mqtts", "ws"]
    tls_refused = {"success": False, "error_type": ERROR_TLS_ERROR}
    result, tries = await _detect(
        {CONF_HOST: "h", CONF_PORT: 8884, CONF_VERIFY_SSL: True},
        answers={"wss": tls_refused},
    )
    checks["a certificate error stops the search"] = tries == [
        (8884, "wss", True)
    ] and (result["error_type"] == ERROR_TLS_ERROR)

    stored = {CONF_HOST: "h", CONF_PORT: 1884, CONF_PROTOCOL: "ws"}
    saved, _, detections = await _options_submit(
        stored, {CONF_PORT: 1884, VERIFY_SSL_FIELD: True}
    )
    checks["options: the port in use keeps its protocol"] = not detections and (
        saved[CONF_PROTOCOL],
        saved[CONF_VERIFY_SSL],
    ) == ("ws", False)
    saved, _, detections = await _options_submit(
        stored, {VERIFY_SSL_FIELD: True}, found=(8883, "mqtts")
    )
    checks["options: a cleared port is detected again"] = detections == [None] and (
        saved[CONF_PORT],
        saved[CONF_PROTOCOL],
        saved[CONF_VERIFY_SSL],
    ) == (8883, "mqtts", True)
    stored = {CONF_HOST: "h", CONF_PORT: 8883, CONF_PROTOCOL: "mqtts"}
    submit = {CONF_PORT: 9999, VERIFY_SSL_FIELD: True, CONF_LOCK_PIN: "1234"}
    saved, shown, _ = await _options_submit(stored, submit)
    fields = {str(key.schema): key for key in shown["data_schema"].schema}
    checks["options: a refused port keeps verification and PIN"] = (
        saved is None
        and shown["errors"] == {"base": ERROR_CANNOT_CONNECT}
        and fields[VERIFY_SSL_FIELD].default() is True
        and CONF_LOCK_PIN in fields
    )

    for name, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
