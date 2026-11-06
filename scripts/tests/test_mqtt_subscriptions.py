#!/usr/bin/env python3
"""Regression test: the integration never subscribes to overlapping filters.

Besides everything under the structure prefix, the integration takes the same
vehicle under any username level ("{prefix}/+/{vehicle_id}/#"), which
TopicParser accepts too. With the default "{prefix}/{mqtt_username}/{vehicle_id}"
structure that filter covers the main one, and brokers such as Mosquitto 2
deliver a message once per matching subscription: every message arrived, and
was processed, twice. The config flow's topic test subscribed to up to four
overlapping filters (main, response, direct and alternative).

This test checks the filters `get_subscription_topics` returns for every
predefined structure: each topic the integration received before is matched
exactly once, and no other topic is matched. It then drives the REAL
`MQTTConnectionManager.async_subscribe_topics` and config-flow
`test_topic_availability` through fake MQTT clients and checks what they
subscribe to.

Run standalone:  python3 scripts/tests/test_mqtt_subscriptions.py
Exits non-zero on failure.
"""

import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import paho.mqtt.client as mqtt

from homeassistant.const import CONF_HOST, CONF_PORT, CONF_PROTOCOL

from custom_components.ovms.config_flow import topic_discovery
from custom_components.ovms.const import (
    CONF_MQTT_USERNAME,
    CONF_TOPIC_PREFIX,
    CONF_TOPIC_STRUCTURE,
    CONF_VEHICLE_ID,
    DEFAULT_PORT,
    DEFAULT_QOS,
    DEFAULT_TOPIC_STRUCTURE,
    TOPIC_STRUCTURES,
)
from custom_components.ovms.mqtt.connection import MQTTConnectionManager
from custom_components.ovms.utils import get_subscription_topics

PREFIX = "ovms"
USERNAME = "owner"
VEHICLE_ID = "car1"
OTHER_VEHICLE_ID = "car2"


def _structure_prefix(structure: str, username: str = USERNAME) -> str:
    """Format a topic structure for the test vehicle."""
    return structure.format(
        prefix=PREFIX, mqtt_username=username, vehicle_id=VEHICLE_ID
    )


def _matches(filters, topic) -> int:
    """How many times a broker delivers ``topic`` to these subscriptions."""
    return sum(mqtt.topic_matches_sub(sub, topic) for sub in filters)


def _check(name, cond, results):
    """Record and print one check."""
    results.append(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


class _FakeHass:
    """Minimal hass stub that runs executor jobs inline."""

    async def async_add_executor_job(self, func, *args):
        """Run the job inline."""
        return func(*args)


class _SubscribeRecorder:
    """Stands in for the paho client of MQTTConnectionManager."""

    def __init__(self):
        self.subscriptions = []

    def subscribe(self, topic, qos):
        """Record a subscription."""
        self.subscriptions.append((topic, qos))


def _no_callback(*_args):
    """Stand in until the code under test sets a callback."""


class _ProbeClient:
    """Fake paho client for test_topic_availability.

    It connects at once, delivers one metric when the loop starts and answers
    the probe's command on its response topic, so the probe never waits.
    """

    last = None

    def __init__(self, **_kwargs):
        self.subscriptions = []
        self.on_connect = self.on_message = _no_callback
        self.on_disconnect = self.on_log = _no_callback
        self.connect_timeout = None
        _ProbeClient.last = self

    def username_pw_set(self, *_args, **_kwargs):
        """Accept credentials like the real client."""

    def connect(self, *_args):
        """Connect at once, as a reachable broker does."""
        self.on_connect(self, None, {}, 0)

    def loop_start(self):
        """Deliver one retained metric, as the broker does after subscribing."""
        metric = f"{_structure_prefix(DEFAULT_TOPIC_STRUCTURE)}/metric/v/b/soc"
        self.on_message(self, None, SimpleNamespace(topic=metric, payload=b"80"))

    def loop_stop(self):
        """Nothing runs in the background."""

    def disconnect(self):
        """Nothing to close."""

    def subscribe(self, topic, **_kwargs):
        """Record a subscription."""
        self.subscriptions.append(topic)

    def publish(self, topic, *_args, **_kwargs):
        """Answer the probe's command on its response topic, as a module does."""
        response = topic.replace("/command/", "/response/")
        self.on_message(self, None, SimpleNamespace(topic=response, payload=b"ok"))


async def main():
    """Run the checks and return the exit code."""
    print("OVMS MQTT subscription overlap regression test")
    print("-" * 55)
    results = []

    # ---- Every predefined structure: each topic delivered once, none lost ----
    structures = [s for s in TOPIC_STRUCTURES if s != "custom"]
    cases = [(s, _structure_prefix(s)) for s in structures]
    cases.append(
        ("default, empty username", _structure_prefix(DEFAULT_TOPIC_STRUCTURE, ""))
    )
    for name, structure_prefix in cases:
        before = [f"{structure_prefix}/#", f"{PREFIX}/+/{VEHICLE_ID}/#"]
        after = get_subscription_topics(structure_prefix, PREFIX, VEHICLE_ID)
        samples = [
            f"{structure_prefix}/metric/v/b/soc",
            f"{structure_prefix}/client/rr/response/abc123",
            f"{PREFIX}/someone-else/{VEHICLE_ID}/metric/v/b/soc",
            f"{PREFIX}/{USERNAME}/{OTHER_VEHICLE_ID}/metric/v/b/soc",
            f"{PREFIX}/{OTHER_VEHICLE_ID}/metric/v/b/soc",
        ]
        _check(
            f"{name}: every topic received before arrives exactly once {after}",
            all(
                _matches(after, topic) == (1 if _matches(before, topic) else 0)
                for topic in samples
            ),
            results,
        )

    _check(
        "default structure subscribes to the any-username filter alone",
        get_subscription_topics(
            _structure_prefix(DEFAULT_TOPIC_STRUCTURE), PREFIX, VEHICLE_ID
        )
        == [f"{PREFIX}/+/{VEHICLE_ID}/#"],
        results,
    )
    _check(
        "{prefix}/{vehicle_id} keeps both filters, as they do not overlap",
        len(
            get_subscription_topics(
                _structure_prefix("{prefix}/{vehicle_id}"), PREFIX, VEHICLE_ID
            )
        )
        == 2,
        results,
    )
    _check(
        "no topic prefix -> only the structure prefix filter",
        get_subscription_topics("custom/car1", "", VEHICLE_ID) == ["custom/car1/#"],
        results,
    )

    # ---- The connection manager subscribes once ----
    config = {
        CONF_TOPIC_PREFIX: PREFIX,
        CONF_MQTT_USERNAME: USERNAME,
        CONF_VEHICLE_ID: VEHICLE_ID,
        CONF_TOPIC_STRUCTURE: DEFAULT_TOPIC_STRUCTURE,
    }
    manager = MQTTConnectionManager(_FakeHass(), config, None, None)
    manager.client = _SubscribeRecorder()
    manager.connected = True
    await manager.async_subscribe_topics()
    _check(
        "MQTTConnectionManager subscribes to one filter",
        manager.client.subscriptions == [(f"{PREFIX}/+/{VEHICLE_ID}/#", DEFAULT_QOS)],
        results,
    )

    # ---- The config-flow topic test subscribes like the integration ----
    probe_config = {
        **config,
        CONF_HOST: "127.0.0.1",
        CONF_PORT: DEFAULT_PORT,
        CONF_PROTOCOL: "mqtt",
    }
    real_mqtt = topic_discovery.mqtt
    topic_discovery.mqtt = SimpleNamespace(
        Client=_ProbeClient, MQTTv5=mqtt.MQTTv5, MQTTv311=mqtt.MQTTv311
    )
    try:
        result = await topic_discovery.test_topic_availability(
            _FakeHass(), probe_config
        )
    finally:
        topic_discovery.mqtt = real_mqtt
    _check("topic test succeeds", result.get("success") is True, results)
    _check(
        "topic test subscribes to the same single filter",
        _ProbeClient.last.subscriptions == [f"{PREFIX}/+/{VEHICLE_ID}/#"],
        results,
    )
    _check(
        "topic test still receives its command response",
        result["debug_info"].get("responses_received") == 1,
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
