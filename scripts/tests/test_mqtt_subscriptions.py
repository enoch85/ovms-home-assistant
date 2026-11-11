#!/usr/bin/env python3
"""Regression test: one MQTT subscription per vehicle, whatever the broker allows.

Besides everything under the structure prefix, the integration takes the same
vehicle under any username level ("{prefix}/+/{vehicle_id}/#"), which
TopicParser accepts too. With the default "{prefix}/{mqtt_username}/{vehicle_id}"
structure that filter covers the main one, and brokers such as Mosquitto 2
deliver a message once per matching subscription: every message arrived, and
was processed, twice. The config flow's topic test subscribed to up to four
overlapping filters (main, response, direct and alternative).

A broker that authorizes subscriptions per user refuses the wider filter,
though: Mosquitto's dynamic security plugin does, and so does the OVMS server's
own broker, whose ACL check only permits topics starting with
"ovms/<username>/". Subscribing to the wider filter alone delivered nothing at
all there - no data, no command responses - so the structure prefix replaces
it when the broker refuses it.

This test checks, for every predefined structure, that each topic the
integration received before is matched exactly once, whether the broker
grants the wider filter or refuses it. It then drives the REAL
`MQTTConnectionManager` and config-flow `test_topic_availability` through fake
MQTT clients that grant or refuse subscriptions like such brokers do.

Run standalone:  python3 scripts/tests/test_mqtt_subscriptions.py
Exits non-zero on failure.
"""

# The subscription answer is handled in private methods on purpose.
# pylint: disable=protected-access

import asyncio
import logging
import os
import sys
import threading
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import paho.mqtt.client as mqtt
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.reasoncodes import ReasonCode

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
    LOGGER_NAME,
    MQTT_SUBACK_FAILURE,
    TOPIC_STRUCTURES,
)
from custom_components.ovms.mqtt.connection import MQTTConnectionManager
from custom_components.ovms.utils import (
    get_subscription_topics,
    is_subscription_refused,
)

PREFIX = "ovms"
USERNAME = "owner"
VEHICLE_ID = "car1"
OTHER_VEHICLE_ID = "car2"
ANY_USERNAME = f"{PREFIX}/+/{VEHICLE_ID}/#"
OWN_TOPICS = f"{PREFIX}/{USERNAME}/{VEHICLE_ID}/#"
GRANTED = ReasonCode(PacketTypes.SUBACK, "Granted QoS 1")
NOT_AUTHORIZED = ReasonCode(PacketTypes.SUBACK, "Not authorized")


def _structure_prefix(structure: str, username: str = USERNAME) -> str:
    """Format a topic structure for the test vehicle."""
    return structure.format(
        prefix=PREFIX, mqtt_username=username, vehicle_id=VEHICLE_ID
    )


def _matches(filters, topic) -> int:
    """How many times a broker delivers ``topic`` to these subscriptions."""
    return sum(mqtt.topic_matches_sub(sub, topic) for sub in filters)


def _effective(topics, refused) -> list:
    """The filters in effect once the broker answered, refused ones replaced."""
    effective = []
    for topic, replacement in topics.items():
        if topic not in refused:
            effective.append(topic)
        elif replacement:
            effective.append(replacement)
    return effective


def _own_topics_only(topic_filter: str) -> bool:
    """The OVMS server's ACL check (ApiHttpMqapi.pm, /mqapi/acl).

    A plain prefix test on the filter: anything not starting with
    "ovms/<username>/" is refused, a "+" in the username level included.
    """
    return topic_filter.startswith(f"{PREFIX}/{USERNAME}/")


def _check(name, cond, results):
    """Record and print one check."""
    results.append(cond)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")


class _Records(logging.Handler):
    """Collects what the integration logs."""

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def messages(self, level):
        """The messages logged at ``level``."""
        return [r.getMessage() for r in self.records if r.levelno == level]


class _FakeHass:
    """Minimal hass stub that runs executor jobs inline."""

    async def async_add_executor_job(self, func, *args):
        """Run the job inline."""
        return func(*args)


class _BrokerClient:
    """Stands in for the paho client of MQTTConnectionManager.

    Each subscription is answered the way paho does it: from paho's own thread,
    and here deliberately before subscribe() has returned its message ID.
    ``allowed`` decides whether the broker grants a filter; ``mqtt311`` answers
    with the plain return codes paho passes for MQTT 3.1.1.
    """

    def __init__(self, allowed=lambda _filter: True, mqtt311=False):
        self.allowed = allowed
        self.mqtt311 = mqtt311
        self.subscriptions = []
        self.on_subscribe = None
        self._mid = 0
        self._answers = []

    def subscribe(self, topic, qos):
        """Record a subscription and answer it from another thread."""
        self._mid += 1
        self.subscriptions.append(topic)
        granted = self.allowed(topic)
        if self.mqtt311:
            args = (self, None, self._mid, (qos if granted else MQTT_SUBACK_FAILURE,))
        else:
            args = (self, None, self._mid, [GRANTED if granted else NOT_AUTHORIZED])
        answer = threading.Thread(target=self.on_subscribe, args=args)
        self._answers.append(answer)
        answer.start()
        # Give the answer every chance to be handled before this returns.
        time.sleep(0.05)
        return mqtt.MQTT_ERR_SUCCESS, self._mid

    def settle(self):
        """Wait for every answer, including those of replacement filters."""
        while self._answers:
            self._answers.pop(0).join()


def _no_callback(*_args):
    """Stand in until the code under test sets a callback."""


class _ProbeClient:
    """Fake paho client for test_topic_availability: a broker in miniature.

    Subscriptions are granted or refused by ``allowed`` and answered after
    on_connect has returned, as paho does. Only granted filters get messages:
    one retained metric when the loop starts, and the answer to the probe's
    command on its response topic.
    """

    allowed = staticmethod(lambda _filter: True)
    last = None

    def __init__(self, **_kwargs):
        self.subscriptions = []
        self.active = []
        self._unanswered = []
        self._mid = 0
        self.on_connect = self.on_message = self.on_subscribe = _no_callback
        self.on_disconnect = self.on_log = _no_callback
        self.connect_timeout = None
        _ProbeClient.last = self

    def username_pw_set(self, *_args, **_kwargs):
        """Accept credentials like the real client."""

    def connect(self, *_args):
        """Connect at once, as a reachable broker does."""
        self.on_connect(self, None, {}, 0)

    def subscribe(self, topic, **_kwargs):
        """Record a subscription; the broker answers it in loop_start."""
        self._mid += 1
        self.subscriptions.append(topic)
        self._unanswered.append((self._mid, topic))
        return mqtt.MQTT_ERR_SUCCESS, self._mid

    def loop_start(self):
        """Answer the subscriptions, then deliver one retained metric."""
        while self._unanswered:
            mid, topic = self._unanswered.pop(0)
            granted = _ProbeClient.allowed(topic)
            if granted:
                self.active.append(topic)
            self.on_subscribe(self, None, mid, [GRANTED if granted else NOT_AUTHORIZED])
        self._deliver(f"{_structure_prefix(DEFAULT_TOPIC_STRUCTURE)}/metric/v/b/soc")

    def _deliver(self, topic):
        """Hand a message to on_message if a granted filter matches it."""
        if _matches(self.active, topic):
            self.on_message(self, None, SimpleNamespace(topic=topic, payload=b"80"))

    def loop_stop(self):
        """Nothing runs in the background."""

    def disconnect(self):
        """Nothing to close."""

    def publish(self, topic, *_args, **_kwargs):
        """Answer the probe's command on its response topic, as a module does."""
        self._deliver(topic.replace("/command/", "/response/"))


async def _probe(config, allowed):
    """Run the config flow's topic test against a broker that grants ``allowed``."""
    real_mqtt = topic_discovery.mqtt
    _ProbeClient.allowed = staticmethod(allowed)
    topic_discovery.mqtt = SimpleNamespace(
        Client=_ProbeClient, MQTTv5=mqtt.MQTTv5, MQTTv311=mqtt.MQTTv311
    )
    try:
        return await topic_discovery.test_topic_availability(_FakeHass(), config)
    finally:
        topic_discovery.mqtt = real_mqtt


async def main():
    """Run the checks and return the exit code."""
    print("OVMS MQTT subscription regression test")
    print("-" * 55)
    results = []
    records = _Records()
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(records)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # ---- Every predefined structure: each topic delivered once, none lost ----
    structures = [s for s in TOPIC_STRUCTURES if s != "custom"]
    cases = [(s, _structure_prefix(s)) for s in structures]
    cases.append(
        ("default, empty username", _structure_prefix(DEFAULT_TOPIC_STRUCTURE, ""))
    )
    for name, structure_prefix in cases:
        before = {f"{structure_prefix}/#": None, ANY_USERNAME: None}
        after = get_subscription_topics(structure_prefix, PREFIX, VEHICLE_ID)
        samples = [
            f"{structure_prefix}/metric/v/b/soc",
            f"{structure_prefix}/client/rr/response/abc123",
            f"{PREFIX}/someone-else/{VEHICLE_ID}/metric/v/b/soc",
            f"{PREFIX}/{USERNAME}/{OTHER_VEHICLE_ID}/metric/v/b/soc",
            f"{PREFIX}/{OTHER_VEHICLE_ID}/metric/v/b/soc",
        ]
        for broker, refused in (("grants", set()), ("refuses", {ANY_USERNAME})):
            was, now = _effective(before, refused), _effective(after, refused)
            _check(
                f"{name}, broker {broker} {ANY_USERNAME}: every topic received "
                f"before arrives exactly once {now}",
                all(
                    _matches(now, topic) == (1 if _matches(was, topic) else 0)
                    for topic in samples
                ),
                results,
            )

    _check(
        "default structure: the any-username filter alone, the structure prefix "
        "replacing it if refused",
        get_subscription_topics(
            _structure_prefix(DEFAULT_TOPIC_STRUCTURE), PREFIX, VEHICLE_ID
        )
        == {ANY_USERNAME: OWN_TOPICS},
        results,
    )
    _check(
        "{prefix}/{vehicle_id} keeps both filters, as they do not overlap",
        get_subscription_topics(
            _structure_prefix("{prefix}/{vehicle_id}"), PREFIX, VEHICLE_ID
        )
        == {f"{PREFIX}/{VEHICLE_ID}/#": None, ANY_USERNAME: None},
        results,
    )
    _check(
        "no topic prefix -> only the structure prefix filter",
        get_subscription_topics("custom/car1", "", VEHICLE_ID)
        == {"custom/car1/#": None},
        results,
    )
    _check(
        "a refusal is recognised for MQTT 5 reason codes and MQTT 3.1.1 return "
        "codes, a grant is not",
        [
            is_subscription_refused([GRANTED]),
            is_subscription_refused([NOT_AUTHORIZED]),
            is_subscription_refused((DEFAULT_QOS,)),
            is_subscription_refused((MQTT_SUBACK_FAILURE,)),
        ]
        == [False, True, False, True],
        results,
    )

    # ---- The connection manager: one filter, replaced when refused ----
    config = {
        CONF_TOPIC_PREFIX: PREFIX,
        CONF_MQTT_USERNAME: USERNAME,
        CONF_VEHICLE_ID: VEHICLE_ID,
        CONF_TOPIC_STRUCTURE: DEFAULT_TOPIC_STRUCTURE,
    }

    def _manager(client):
        manager = MQTTConnectionManager(_FakeHass(), dict(config), None, None)
        manager.client = client
        manager._setup_callbacks()
        manager.connected = True
        return manager

    client = _BrokerClient()
    await _manager(client).async_subscribe_topics()
    client.settle()
    _check(
        "a broker that grants it: MQTTConnectionManager subscribes to one filter",
        client.subscriptions == [ANY_USERNAME],
        results,
    )

    for label, mqtt311 in (("MQTT 5", False), ("MQTT 3.1.1", True)):
        records.records.clear()
        client = _BrokerClient(allowed=_own_topics_only, mqtt311=mqtt311)
        manager = _manager(client)
        await manager.async_subscribe_topics()
        client.settle()
        _check(
            f"{label}, the OVMS server's ACL: the refused filter is replaced by "
            "the structure prefix, although the refusal came before subscribe() "
            "returned",
            client.subscriptions == [ANY_USERNAME, OWN_TOPICS],
            results,
        )
        await manager.async_subscribe_topics()
        client.settle()
        _check(
            f"{label}: subscribing again (platforms loaded, reconnection) goes "
            "straight to the structure prefix, logged once at info",
            (
                client.subscriptions[2:],
                len([m for m in records.messages(logging.INFO) if "refused" in m]),
                records.messages(logging.WARNING),
            )
            == ([OWN_TOPICS], 1, []),
            results,
        )

    records.records.clear()
    client = _BrokerClient(allowed=lambda _filter: False)
    await _manager(client).async_subscribe_topics()
    client.settle()
    _check(
        "a broker that refuses even the structure prefix gets a warning: no data "
        "can arrive",
        any(OWN_TOPICS in m for m in records.messages(logging.WARNING)),
        results,
    )

    # ---- The config-flow topic test subscribes like the integration ----
    probe_config = {
        **config,
        CONF_HOST: "127.0.0.1",
        CONF_PORT: DEFAULT_PORT,
        CONF_PROTOCOL: "mqtt",
    }
    result = await _probe(probe_config, lambda _filter: True)
    _check("topic test succeeds", result.get("success") is True, results)
    _check(
        "topic test subscribes to the same single filter",
        _ProbeClient.last.subscriptions == [ANY_USERNAME],
        results,
    )
    _check(
        "topic test still receives its command response",
        result["debug_info"].get("responses_received") == 1,
        results,
    )

    result = await _probe(probe_config, _own_topics_only)
    _check(
        "topic test against the OVMS server's ACL: refused filter replaced, "
        "the metric and the command response arrive",
        (
            _ProbeClient.last.subscriptions,
            result["debug_info"].get("refused_subscription"),
            result["debug_info"].get("messages_received"),
            result["debug_info"].get("responses_received"),
        )
        == ([ANY_USERNAME, OWN_TOPICS], ANY_USERNAME, 2, 1),
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
