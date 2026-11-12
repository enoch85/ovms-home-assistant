#!/usr/bin/env python3
"""Broker port and protocol detection in the setup and options forms (#281).

Runs the real probe against local listeners that answer like a broker's MQTT
and WebSocket listeners, plain and with TLS, and the real setup and options
flows around it.

Run standalone:  python3 scripts/tests/test_broker_detection.py
Exits non-zero on failure.
"""

# pylint: disable=wrong-import-position,protected-access

import asyncio
import datetime
import os
import socket
import ssl
import sys
import tempfile
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import homeassistant  # noqa: F401  # pylint: disable=unused-import
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from custom_components.ovms import config_flow
from custom_components.ovms.config_flow import mqtt_connection, options_flow
from custom_components.ovms.const import (
    CONF_HOST,
    CONF_LOCK_PIN,
    CONF_PORT,
    CONF_PROTOCOL,
    CONF_VERIFY_SSL,
    ERROR_CANNOT_CONNECT,
    VERIFY_SSL_FIELD,
)

CONNACK = b"\x20\x02\x00\x00"
UPGRADED = b"HTTP/1.1 101 Switching Protocols\r\n\r\n"


def _check(name, cond, results):
    results.append(bool(cond))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


def _server_context():
    """A TLS server context with a throwaway self-signed certificate."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    folder = tempfile.mkdtemp()
    cert_path, key_path = os.path.join(folder, "c.pem"), os.path.join(folder, "k.pem")
    with open(cert_path, "wb") as file:
        file.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(key_path, "wb") as file:
        file.write(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    return context


def _listener(answer, tls=None):
    """Listen on a free port; answer the first bytes of a connection, or close."""
    server = socket.create_server(("127.0.0.1", 0))

    def serve():
        while True:
            conn, _ = server.accept()
            try:
                if tls:
                    conn = tls.wrap_socket(conn, server_side=True)
                reply = answer(conn.recv(1024))
                if reply:
                    conn.sendall(reply)
            except OSError:
                pass
            finally:
                conn.close()

    threading.Thread(target=serve, daemon=True).start()
    return server.getsockname()[1]


def _mqtt(data):
    return CONNACK if data[:1] == b"\x10" else None


def _websocket(data):
    return UPGRADED if data.startswith(b"GET /mqtt ") else None


class _Entry:
    """Config entry stand-in for the options flow."""

    entry_id = "test_entry"
    options = {}

    def __init__(self, data):
        self.data = data


async def _options_submit(stored, user_input, detected):
    """Submit the options form; return (saved data or None, form shown, probes)."""
    probes = []

    async def detect(_hass, host, port):
        probes.append((host, port))
        return detected

    class _Flow(options_flow.OVMSOptionsFlow):
        config_entry = _Entry(stored)

    options_flow.async_detect_broker = detect
    flow = _Flow(_Flow.config_entry)
    saved, shown = {}, {}
    flow.async_create_entry = lambda **kw: saved.update(kw) or kw
    flow.async_show_form = lambda **kw: shown.update(kw) or kw
    await flow.async_step_init(dict(user_input))
    return saved.get("data"), shown, probes


async def main():
    print("OVMS broker detection test (issue #281)")
    print("-" * 60)
    results = []
    tls = _server_context()
    closed = socket.create_server(("127.0.0.1", 0))
    closed_port = closed.getsockname()[1]
    closed.close()

    ports = {
        "mqtt": _listener(_mqtt),
        "ws": _listener(_websocket),
        "mqtts": _listener(_mqtt, tls),
        "wss": _listener(_websocket, tls),
        None: _listener(lambda _: b"HTTP/1.1 404 Not Found\r\n\r\n"),
    }
    for protocol, port in ports.items():
        got = mqtt_connection._detect_protocol("127.0.0.1", port)
        _check(
            f"a {protocol or 'non-MQTT'} listener is {got}", got == protocol, results
        )
    got = mqtt_connection._detect_protocol("127.0.0.1", closed_port)
    _check("a closed port is None", got is None, results)
    got = mqtt_connection._detect_protocol("192.168.1..10", closed_port)
    _check("an invalid host name is None", got is None, results)

    class _Hass:
        async def async_add_executor_job(self, func, *args):
            return func(*args)

    mqtt_connection.STANDARD_BROKER_PORTS = (closed_port, ports["mqtts"], ports["mqtt"])
    got = await mqtt_connection.async_detect_broker(_Hass(), "127.0.0.1", None)
    _check(
        "without a port the first one that answers is used",
        got == ("mqtts", ports["mqtts"]),
        results,
    )
    got = await mqtt_connection.async_detect_broker(_Hass(), "127.0.0.1", ports["ws"])
    _check(
        "an entered port is only probed for its protocol",
        got == ("ws", ports["ws"]),
        results,
    )

    stored = {
        CONF_HOST: "broker",
        CONF_PORT: 1884,
        CONF_PROTOCOL: "ws",
        CONF_VERIFY_SSL: False,
    }
    saved, _, probes = await _options_submit(
        stored, {CONF_PORT: 1884, VERIFY_SSL_FIELD: True}, None
    )
    _check(
        "options saved with the port in use keep it, without probing",
        not probes
        and (saved[CONF_PROTOCOL], saved[CONF_PORT], saved[CONF_VERIFY_SSL])
        == ("ws", 1884, False),
        results,
    )
    saved, _, probes = await _options_submit(
        stored, {VERIFY_SSL_FIELD: True}, ("mqtts", 8883)
    )
    _check(
        "a cleared port is detected again",
        probes == [("broker", None)]
        and (saved[CONF_PROTOCOL], saved[CONF_PORT], saved[CONF_VERIFY_SSL])
        == ("mqtts", 8883, True),
        results,
    )
    stored = {
        CONF_HOST: "broker",
        CONF_PORT: 8883,
        CONF_PROTOCOL: "mqtts",
        CONF_VERIFY_SSL: True,
        CONF_LOCK_PIN: "1234",
    }
    submit = {CONF_PORT: 9999, VERIFY_SSL_FIELD: True, CONF_LOCK_PIN: "1234"}
    saved, shown, _ = await _options_submit(stored, submit, None)
    fields = {str(key.schema): key for key in shown["data_schema"].schema}
    _check(
        "a port without a broker is refused, verification and PIN kept",
        saved is None
        and shown["errors"] == {"base": ERROR_CANNOT_CONNECT}
        and fields[VERIFY_SSL_FIELD].default() is True
        and CONF_LOCK_PIN in fields,
        results,
    )

    tested = []

    async def detect(_hass, _host, _port):
        return ("mqtt", 1883)

    async def connection_test(_hass, config):
        tested.append(dict(config))
        return {"success": True}

    config_flow.async_detect_broker = detect
    config_flow.test_mqtt_connection = connection_test
    flow = config_flow.OVMSConfigFlow()
    flow.async_show_form = lambda **kw: kw
    await flow.async_step_user({CONF_HOST: "broker", VERIFY_SSL_FIELD: True})
    _check(
        "the setup tests and keeps the detected protocol and port",
        tested
        and (
            flow.mqtt_config[CONF_PROTOCOL],
            flow.mqtt_config[CONF_PORT],
            flow.mqtt_config[CONF_VERIFY_SSL],
        )
        == ("mqtt", 1883, False),
        results,
    )

    print("-" * 60)
    if all(results):
        print(f"All {len(results)} checks passed.")
        return 0
    print(f"{results.count(False)} of {len(results)} checks FAILED.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
