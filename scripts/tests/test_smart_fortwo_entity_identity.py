#!/usr/bin/env python3
"""Regression test: Smart ForTwo definitions must not orphan existing entities.

Home Assistant identifies an entity by its platform plus its unique ID. The
unique ID is derived from the MQTT topic alone, so renaming a metric, changing
its unit or giving it a definition is harmless. The PLATFORM, however, follows
from the definition (a binary device class makes a binary sensor): giving a
metric that already exists in the field a definition of the other kind creates
a second entity and leaves the old one orphaned and unavailable for good.

Three Smart 453 metrics of firmware 3.3.006+ had no definition and were created
through the generic fallback. This pins the platform they had then:

  * xsq.bms.interlock.hvplug / .service - binary sensors (the generic "lock"
    pattern matched "interlock");
  * xsq.evc.plug.detected - a yes/no sensor (no pattern matched).

This drives the REAL ``TopicParser`` and ``EntityFactory._generate_unique_ids``.

Run standalone:  python3 scripts/tests/test_smart_fortwo_entity_identity.py
Exits non-zero on failure.
"""

import hashlib
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
logging.disable(logging.CRITICAL)

from custom_components.ovms.metrics import METRIC_DEFINITIONS
from custom_components.ovms.mqtt.entity_factory import EntityFactory
from custom_components.ovms.mqtt.entity_registry import EntityRegistry
from custom_components.ovms.mqtt.topic_parser import TopicParser

CONFIG = {
    "topic_prefix": "ovms",
    "mqtt_username": "u",
    "vehicle_id": "car",
    "topic_structure": "{prefix}/{mqtt_username}/{vehicle_id}",
}

# metric -> platform it has had since firmware 3.3.006 started publishing it
PINNED_PLATFORMS = {
    "xsq.bms.interlock.hvplug": "binary_sensor",
    "xsq.bms.interlock.service": "binary_sensor",
    "xsq.evc.plug.detected": "sensor",
}


class _FactoryConfig:
    """The two attributes ``_generate_unique_ids`` reads."""

    config = CONFIG
    _config_entry_id = "entry1"


def _check(name, got, want, results):
    ok = got == want
    results.append(ok)
    print(
        f"  {'PASS' if ok else 'FAIL'}  {name}: {got!r}"
        + ("" if ok else f" != {want!r}")
    )


def main():
    print("OVMS Smart ForTwo entity identity regression test")
    print("-" * 55)
    results = []

    for metric, platform in PINNED_PLATFORMS.items():
        topic = "ovms/u/car/metric/" + metric.replace(".", "/")
        parsed = TopicParser(CONFIG, EntityRegistry()).parse_topic(topic, "yes")

        _check(f"{metric} is defined", metric in METRIC_DEFINITIONS, True, results)
        _check(f"{metric} platform", parsed["entity_type"], platform, results)

        # The unique ID must depend on nothing but the entry, vehicle and topic.
        topic_hash = hashlib.md5(topic.encode()).hexdigest()[:6]
        unique_id = EntityFactory._generate_unique_ids(
            _FactoryConfig, topic, dict(parsed)
        )["unique_id"]
        _check(
            f"{metric} unique id",
            unique_id,
            f"ovms_entry1_car_metric_{metric.replace('.', '_')}_{topic_hash}",
            results,
        )

    print("-" * 55)
    if all(results):
        print(f"All {len(results)} checks passed.")
        return 0
    print(f"{results.count(False)} of {len(results)} checks FAILED.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
