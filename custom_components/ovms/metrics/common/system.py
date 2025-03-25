"""System metrics for OVMS integration."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
)
from homeassistant.const import (
    UnitOfTime,
    UnitOfInformation,
)
from homeassistant.helpers.entity import EntityCategory

# System metrics
SYSTEM_METRICS = {
    "m.freeram": {
        "name": "Free RAM",
        "description": "Total amount of free RAM in bytes",
        "icon": "mdi:memory",
        "device_class": SensorDeviceClass.DATA_SIZE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfInformation.BYTES,
        "category": "system",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "m.hardware": {
        "name": "Hardware Info",
        "description": "Base module hardware info",
        "icon": "mdi:information",
        "category": "system",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "m.monotonic": {
        "name": "Uptime",
        "description": "Uptime in seconds",
        "icon": "mdi:timer-outline",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTime.SECONDS,
        "category": "system",
    },
    "m.obdc2ecu.on": {
        "name": "OBD2ECU Process",
        "description": "Is the OBD2ECU process currently on",
        "icon": "mdi:car-connected",
        "category": "system",
        "device_class": BinarySensorDeviceClass.POWER,
    },
    "m.serial": {
        "name": "Serial Number",
        "description": "Module serial number",
        "icon": "mdi:identifier",
        "category": "system",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "m.tasks": {
        "name": "Task Count",
        "description": "Task count (use module tasks to list)",
        "icon": "mdi:console",
        "category": "system",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "m.time.utc": {
        "name": "UTC Time",
        "description": "Current UTC time",
        "icon": "mdi:clock",
        "device_class": SensorDeviceClass.TIMESTAMP,
        "category": "system",
    },
    "m.version": {
        "name": "Firmware Version",
        "description": "Firmware version",
        "icon": "mdi:package-up",
        "category": "system",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "m.egpio.input": {
        "name": "GPIO Input Ports",
        "description": "EGPIO input port state (ports 0…9, present=high)",
        "icon": "mdi:integrated-circuit-chip",
        "category": "system",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "m.egpio.monitor": {
        "name": "GPIO Monitoring Ports",
        "description": "EGPIO input monitoring ports",
        "icon": "mdi:integrated-circuit-chip",
        "category": "system",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "m.egpio.output": {
        "name": "GPIO Output Ports",
        "description": "EGPIO output port state",
        "icon": "mdi:integrated-circuit-chip",
        "category": "system",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "s.v2.connected": {
        "name": "V2 Server Connected",
        "description": "V2 (MP) server connected",
        "icon": "mdi:server-network",
        "category": "system",
        "device_class": BinarySensorDeviceClass.CONNECTIVITY,
    },
    "s.v2.peers": {
        "name": "V2 Clients Connected",
        "description": "Number of V2 clients connected",
        "icon": "mdi:account-multiple",
        "category": "system",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "s.v3.connected": {
        "name": "V3 Server Connected",
        "description": "V3 (MQTT) server connected",
        "icon": "mdi:server-network",
        "category": "system",
        "device_class": BinarySensorDeviceClass.CONNECTIVITY,
    },
    "s.v3.peers": {
        "name": "V3 Clients Connected",
        "description": "Number of V3 clients connected",
        "icon": "mdi:account-multiple",
        "category": "system",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
}
