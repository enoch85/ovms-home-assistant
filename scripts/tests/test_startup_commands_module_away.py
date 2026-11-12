#!/usr/bin/env python3
"""Regression test: the commands the integration sends by itself at startup.

At every start the integration sends the module its time zone, asks it for its
metric units and, when entities are missing, for a full publish. OVMS publishes
retained, so the broker hands over "V3 Server Connected: on" whether the module
is there or not; a module that was asleep, offline or still reconnecting (after
a broker restart, say) let every one of those commands time out, each with a
warning blaming the firmware and a second warning from its caller.

Now the module counts as reachable only once it published something live (the
broker clears the retain flag on a live message), and as away when its will
("no" on s.v3.connected) is seen or a command went unanswered before that:

  * while it is away nothing more is sent, and one info line says why;
  * the time zone and the unit query are sent again once it is seen again;
  * a module that publishes but does not answer gets one actionable warning;
  * the generic timeout warning is kept for commands a user sends.

Run standalone:  python3 scripts/tests/test_startup_commands_module_away.py
Exits non-zero on failure.
"""

# This drives the client's private startup-command path on purpose.
# pylint: disable=protected-access

import asyncio
import logging
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from custom_components.ovms import mqtt as ovms_mqtt
from custom_components.ovms.const import (
    COMMAND_TIMEOUT_ERROR,
    CONF_VEHICLE_ID,
    DEFAULT_COMMAND_TIMEOUT,
    DOMAIN,
    LOGGER_NAME,
    METRIC_REFRESH_COMMAND,
    METRIC_UNITS_COMMAND,
    MODULE_TIMEZONE_COMMAND,
)
from custom_components.ovms.mqtt import OVMSMQTTClient
from custom_components.ovms.mqtt.command_handler import CommandHandler
from custom_components.ovms.mqtt.connection import MQTTConnectionManager

CONFIG = {
    "topic_prefix": "ovms",
    "mqtt_username": "u",
    "vehicle_id": "car",
    "topic_structure": "{prefix}/{mqtt_username}/{vehicle_id}",
    "config_entry_id": "entry1",
}
BASE = "ovms/u/car/"
CONNECTED = BASE + "metric/s/v3/connected"
SOC = BASE + "metric/v/b/soc"
POSIX_TIME_ZONE = "NZST-12NZDT,M9.5.0,M4.1.0/3"
TIME_ZONE_COMMAND = MODULE_TIMEZONE_COMMAND.format(timezone=POSIX_TIME_ZONE)
ANSWER = {"success": True, "response": "Parameter has been set."}
TIMEOUT = {"success": False, "error": COMMAND_TIMEOUT_ERROR}

# Deferred commands go out right away here, and the zone is not looked up.
ovms_mqtt.DEFERRED_COMMAND_DELAY = 0
ovms_mqtt.get_module_time_zone = lambda _time_zone: POSIX_TIME_ZONE


class _Records(logging.Handler):
    """Collects what the integration logs."""

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def levels(self, level):
        return [r for r in self.records if r.levelno == level]

    def messages(self, level):
        return [r.getMessage() for r in self.levels(level)]


class _FakeEntry:
    def __init__(self, background_tasks):
        self._background_tasks = background_tasks

    def async_create_background_task(self, hass, coro, name=None):
        task = asyncio.get_running_loop().create_task(coro)
        self._background_tasks.append(task)
        return task


class _FakeHass:
    """Just enough of Home Assistant for the client."""

    def __init__(self):
        self.data = {}
        self.background_tasks = []
        entry = _FakeEntry(self.background_tasks)
        self.config_entries = SimpleNamespace(
            async_get_entry=lambda entry_id: (
                entry if entry_id == CONFIG["config_entry_id"] else None
            )
        )
        self.config = SimpleNamespace(time_zone="Pacific/Auckland")
        self.loop = asyncio.get_running_loop()

    async def async_add_executor_job(self, func, *args):
        return func(*args)

    async def settle(self):
        """Wait for background tasks, including those they start."""
        while not all(task.done() for task in self.background_tasks):
            await asyncio.gather(*self.background_tasks)


class _RecordingFactory:
    async def async_create_entities(self, topic, payload, entity_data):
        return None


def _client(answers):
    """A real client whose command channel answers from ``answers``.

    ``answers`` maps a command to a result or to a list of successive results.
    """
    hass = _FakeHass()
    client = OVMSMQTTClient(hass, dict(CONFIG))
    client.entity_factory = _RecordingFactory()
    client._setup_complete.set()
    client.connected = True
    client._count_missing_registry_entities = lambda: 0
    sent = []

    async def _send_command(**kwargs):
        command = kwargs["command"]
        sent.append((command, kwargs.get("quiet")))
        answer = answers[command]
        return answer.pop(0) if isinstance(answer, list) else answer

    client.async_send_command = _send_command
    return client, hass, sent


def _check(name, got, want, results):
    ok = got == want
    results.append(ok)
    print(
        f"  {'PASS' if ok else 'FAIL'}  {name}: {got!r}"
        + ("" if ok else f" != {want!r}")
    )


async def main():
    print("OVMS startup commands with the module away regression test")
    print("-" * 55)
    results = []
    records = _Records()
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(records)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # ---- 1) a module that answers: sent once, quietly, nothing deferred --
    client, hass, sent = _client({TIME_ZONE_COMMAND: ANSWER})
    await client._async_set_module_time_zone()
    _check(
        "an answering module gets the time zone, sent as a quiet command",
        (sent, client._deferred_commands, records.levels(logging.WARNING)),
        ([(TIME_ZONE_COMMAND, True)], {}, []),
        results,
    )
    await client.command_handler.async_shutdown()

    # ---- 2) its will is on the broker: nothing is sent until it is back --
    records.records.clear()
    client, hass, sent = _client(
        {TIME_ZONE_COMMAND: ANSWER, METRIC_REFRESH_COMMAND: ANSWER}
    )
    await client._on_message_received(CONNECTED, "no", True)
    await client._async_set_module_time_zone()
    client._entry_had_entities = False  # a first setup always asks for everything
    await client._async_startup_metric_refresh(None)
    _check(
        "with the module's will retained, no startup command is sent; both wait",
        (sent, list(client._deferred_commands)),
        ([], [TIME_ZONE_COMMAND, METRIC_REFRESH_COMMAND]),
        results,
    )
    _check(
        "one info line says the module is offline, and nothing claims a full "
        "publish was requested",
        (
            [
                m
                for m in records.messages(logging.INFO)
                if "not sent until it publishes again" in m
            ],
            [m for m in records.messages(logging.INFO) if "requesting" in m],
        ),
        (
            [
                "The OVMS module is offline (its MQTT will is on the broker). The "
                "integration's own startup commands are not sent until it "
                "publishes again"
            ],
            [],
        ),
        results,
    )
    await client._on_message_received(SOC, "81", True)
    await client._on_message_received(CONNECTED, "yes", True)
    await client._on_message_received(BASE + "status", "online", False)
    await client._on_message_received(BASE + "client/app/active", "1", False)
    await hass.settle()
    _check(
        "retained data, Home Assistant's own status and other clients do not "
        "count as the module being back",
        (client._module_reachable, sent),
        (False, []),
        results,
    )
    await client._on_message_received(SOC, "80", False)
    await hass.settle()
    _check(
        "the first live metric sends the time zone once, and the refresh this "
        "first setup still needs",
        (
            client._module_reachable,
            sorted(sent),
            client._deferred_commands,
        ),
        (
            True,
            sorted([(TIME_ZONE_COMMAND, True), (METRIC_REFRESH_COMMAND, True)]),
            {},
        ),
        results,
    )
    _check(
        "nothing above info level was logged",
        [r.getMessage() for r in records.records if r.levelno > logging.INFO],
        [],
        results,
    )
    await client.command_handler.async_shutdown()

    # ---- 3) no answer, nothing live seen: one info line, the rest waits --
    records.records.clear()
    client, hass, sent = _client(
        {
            TIME_ZONE_COMMAND: [TIMEOUT, ANSWER],
            METRIC_UNITS_COMMAND: {"success": True, "response": ""},
            METRIC_REFRESH_COMMAND: ANSWER,
        }
    )
    await client._on_message_received(CONNECTED, "yes", True)
    await client._async_set_module_time_zone()
    client._entry_had_entities = False
    await client._async_startup_metric_refresh(None)
    client._request_metric_units()
    await hass.settle()
    _check(
        "after one unanswered command nothing else is sent",
        sent,
        [(TIME_ZONE_COMMAND, True)],
        results,
    )
    _check(
        "one info line says why, and there is no warning",
        (
            [
                m
                for m in records.messages(logging.INFO)
                if "not sent until it publishes again" in m
            ],
            records.levels(logging.WARNING),
        ),
        (
            [
                "The OVMS module did not answer "
                f"'{TIME_ZONE_COMMAND}' within {DEFAULT_COMMAND_TIMEOUT} seconds "
                "and is not publishing anything live, so it is probably asleep, "
                "offline or reconnecting (its retained data looks the same either "
                "way). The integration's own startup commands are not sent until "
                "it publishes again"
            ],
            [],
        ),
        results,
    )
    await client._on_message_received(SOC, "80", False)
    await hass.settle()
    _check(
        "once the module publishes, the time zone, the unit query and the "
        "refresh a first setup needs are sent again",
        sorted(command for command, _quiet in sent[1:]),
        sorted([TIME_ZONE_COMMAND, METRIC_UNITS_COMMAND, METRIC_REFRESH_COMMAND]),
        results,
    )
    await client.command_handler.async_shutdown()

    # ---- 3b) the refresh is decided afresh once the module is back --------
    for label, missing_when_back, expected in (
        (
            "it reconnected and published everything itself: no refresh",
            0,
            [],
        ),
        (
            "it only resumed, entities are still missing: refresh",
            2,
            [METRIC_REFRESH_COMMAND],
        ),
    ):
        records.records.clear()
        client, hass, sent = _client(
            {TIME_ZONE_COMMAND: [TIMEOUT, ANSWER], METRIC_REFRESH_COMMAND: ANSWER}
        )
        missing = [2]
        client._count_missing_registry_entities = lambda: missing[0]
        client._entry_had_entities = True
        await client._async_set_module_time_zone()  # unanswered: module away
        await client._async_startup_metric_refresh(None)  # held back
        held_back = [m for m in records.messages(logging.INFO) if "requesting" in m]
        missing[0] = missing_when_back
        await client._on_message_received(SOC, "80", False)
        await hass.settle()
        _check(
            f"module back, {label}",
            (
                held_back,
                [command for command, _quiet in sent if command != TIME_ZONE_COMMAND],
                len([m for m in records.messages(logging.INFO) if "requesting" in m]),
            ),
            ([], expected, len(expected)),
            results,
        )
        await client.command_handler.async_shutdown()

    # ---- 4) it publishes but does not answer: one actionable warning ------
    records.records.clear()
    client, hass, sent = _client(
        {TIME_ZONE_COMMAND: TIMEOUT, METRIC_REFRESH_COMMAND: TIMEOUT}
    )
    await client._on_message_received(SOC, "80", False)
    await client._async_set_module_time_zone()
    client._entry_had_entities = False
    await client._async_startup_metric_refresh(None)
    await hass.settle()
    warnings = records.levels(logging.WARNING)
    _check(
        "both are sent, neither is deferred, and one warning names the topic "
        "the module has to read",
        (
            len(sent),
            client._deferred_commands,
            len(warnings),
            "ovms/u/car/client/rr/command/+" in warnings[0].getMessage(),
        ),
        (2, {}, 1, True),
        results,
    )
    await client._on_message_received(CONNECTED, "no", True)
    _check(
        "a retained will does not outweigh a live metric",
        client._module_reachable,
        True,
        results,
    )
    await client._on_message_received(CONNECTED, "no", False)
    _check(
        "the will forwarded live means the module is gone",
        client._module_reachable,
        False,
        results,
    )
    await client.command_handler.async_shutdown()

    # ---- 4b) it left while the command waited: no warning, sent later -----
    records.records.clear()
    client, hass, sent = _client({TIME_ZONE_COMMAND: [TIMEOUT, ANSWER]})
    await client._on_message_received(SOC, "80", False)
    send = client.async_send_command

    async def _send_then_leave(**kwargs):
        result = await send(**kwargs)
        if len(sent) == 1:
            await client._on_message_received(CONNECTED, "no", False)
        return result

    client.async_send_command = _send_then_leave
    await client._async_set_module_time_zone()
    _check(
        "a module that left while the command waited gets no warning; the "
        "command waits for it",
        (records.levels(logging.WARNING), list(client._deferred_commands)),
        ([], [TIME_ZONE_COMMAND]),
        results,
    )
    await client._on_message_received(SOC, "79", False)
    await hass.settle()
    _check(
        "... and is sent again when it is back",
        [command for command, _quiet in sent],
        [TIME_ZONE_COMMAND, TIME_ZONE_COMMAND],
        results,
    )
    await client.command_handler.async_shutdown()

    # ---- 4c) it publishes under another username: the warning names both --
    records.records.clear()
    client, hass, sent = _client({TIME_ZONE_COMMAND: TIMEOUT})
    await client._on_message_received("ovms/other/car/metric/v/b/soc", "80", False)
    await client._async_set_module_time_zone()
    warnings = records.messages(logging.WARNING)
    _check(
        "data accepted from another username level: the warning names where it "
        "publishes and where the commands go",
        (
            len(warnings),
            "publishes data under 'ovms/other/car'" in warnings[0],
            "commands go to 'ovms/u/car'" in warnings[0],
        ),
        (1, True, True),
        results,
    )
    await client.command_handler.async_shutdown()

    # ---- 5) the command handler keeps the generic warning for users -------
    class _Connection:
        connected = True

        async def async_publish(self, topic, payload, qos=None):
            return True

    hass = _FakeHass()
    hass.data[DOMAIN] = {
        "entry1": {
            "mqtt_client": SimpleNamespace(
                config={CONF_VEHICLE_ID: "car"}, connection_manager=_Connection()
            )
        }
    }
    handler = CommandHandler(hass, {**CONFIG, CONF_VEHICLE_ID: "car"})
    for quiet, level in ((True, logging.DEBUG), (False, logging.WARNING)):
        records.records.clear()
        result = await handler.async_send_command(
            command="stat", timeout=0, quiet=quiet
        )
        timed_out = [r for r in records.records if "timed out" in r.getMessage()]
        _check(
            f"a timeout with quiet={quiet} is logged at {logging.getLevelName(level)}",
            (result["error"], [r.levelno for r in timed_out]),
            (COMMAND_TIMEOUT_ERROR, [level]),
            results,
        )
    await handler.async_shutdown()

    # ---- 6) the connection manager hands the retain flag on ---------------
    received = []

    async def _on_message(topic, payload, retained):
        received.append((topic, payload, retained))

    manager = MQTTConnectionManager(hass, dict(CONFIG), _on_message, lambda _: None)
    manager.client = SimpleNamespace()
    manager._setup_callbacks()
    manager.client.on_message(
        None, None, SimpleNamespace(topic=SOC, payload=b"80", retain=True)
    )
    await asyncio.sleep(0.05)
    _check(
        "the retain flag of an MQTT message reaches the client",
        received,
        [(SOC, "80", True)],
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
