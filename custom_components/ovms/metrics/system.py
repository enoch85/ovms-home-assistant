"""System metrics for OVMS integration."""
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
)
from homeassistant.const import (
    UnitOfLength,
    UnitOfTime,
)
from homeassistant.helpers.entity import EntityCategory

# Category
CATEGORY_SYSTEM = "system"
CATEGORY_DIAGNOSTIC = "diagnostic"

# System metrics
SYSTEM_METRICS = {
    # System metrics
    "m.freeram": {
        "name": "Free RAM",
        "description": "Total amount of free RAM in bytes",
        "icon": "mdi:memory",
        "category": CATEGORY_SYSTEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "m.hardware": {
        "name": "Hardware Info",
        "description": "Base module hardware info",
        "icon": "mdi:information",
        "category": CATEGORY_SYSTEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "m.monotonic": {
        "name": "Uptime",
        "description": "Uptime in seconds",
        "icon": "mdi:timer-outline",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTime.SECONDS,
        "category": CATEGORY_SYSTEM,
    },
    "m.obdc2ecu.on": {
        "name": "OBD2ECU Process",
        "description": "Is the OBD2ECU process currently on",
        "icon": "mdi:car-connected",
        "category": CATEGORY_SYSTEM,
        "device_class": BinarySensorDeviceClass.POWER,
    },
    "m.serial": {
        "name": "Serial Number",
        "description": "Module serial number",
        "icon": "mdi:identifier",
        "category": CATEGORY_SYSTEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "m.tasks": {
        "name": "Task Count",
        "description": "Task count (use module tasks to list)",
        "icon": "mdi:console",
        "category": CATEGORY_SYSTEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "m.time.utc": {
        "name": "UTC Time",
        "description": "Current UTC time",
        "icon": "mdi:clock",
        "device_class": SensorDeviceClass.TIMESTAMP,
        "category": CATEGORY_SYSTEM,
    },
    "m.version": {
        "name": "Firmware Version",
        "description": "Firmware version",
        "icon": "mdi:package-up",
        "category": CATEGORY_SYSTEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "m.egpio.input": {
        "name": "GPIO Input Ports",
        "description": "EGPIO input port state (ports 0…9, present=high)",
        "icon": "mdi:gpio",
        "category": CATEGORY_SYSTEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "m.egpio.monitor": {
        "name": "GPIO Monitoring Ports",
        "description": "EGPIO input monitoring ports",
        "icon": "mdi:gpio",
        "category": CATEGORY_SYSTEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "m.egpio.output": {
        "name": "GPIO Output Ports",
        "description": "EGPIO output port state",
        "icon": "mdi:gpio",
        "category": CATEGORY_SYSTEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "s.v2.connected": {
        "name": "V2 Server Connected",
        "description": "V2 (MP) server connected",
        "icon": "mdi:server-network",
        "category": CATEGORY_SYSTEM,
        "device_class": BinarySensorDeviceClass.CONNECTIVITY,
    },
    "s.v2.peers": {
        "name": "V2 Clients Connected",
        "description": "Number of V2 clients connected",
        "icon": "mdi:account-multiple",
        "category": CATEGORY_SYSTEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "s.v3.connected": {
        "name": "V3 Server Connected",
        "description": "V3 (MQTT) server connected",
        "icon": "mdi:server-network",
        "category": CATEGORY_SYSTEM,
        "device_class": BinarySensorDeviceClass.CONNECTIVITY,
    },
    "s.v3.peers": {
        "name": "V3 Clients Connected",
        "description": "Number of V3 clients connected",
        "icon": "mdi:account-multiple",
        "category": CATEGORY_SYSTEM,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    
    # Diagnostic metrics
    "v.e.alarm": {
        "name": "Alarm",
        "description": "Alarm sounding state",
        "icon": "mdi:bell-ring",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "category": CATEGORY_DIAGNOSTIC,
    },
    "v.e.awake": {
        "name": "Vehicle Awake",
        "description": "Vehicle is fully awake (switched on by the user)",
        "icon": "mdi:power",
        "device_class": BinarySensorDeviceClass.POWER,
        "category": CATEGORY_DIAGNOSTIC,
    },
    "v.e.c.config": {
        "name": "ECU Configuration Mode",
        "description": "ECU/controller in configuration state",
        "icon": "mdi:wrench",
        "category": CATEGORY_DIAGNOSTIC,
        "device_class": BinarySensorDeviceClass.UPDATE,
    },
    "v.e.c.login": {
        "name": "ECU Login Status",
        "description": "Module logged in at ECU/controller",
        "icon": "mdi:login",
        "category": CATEGORY_DIAGNOSTIC,
        "device_class": BinarySensorDeviceClass.CONNECTIVITY,
    },
    "v.e.drivemode": {
        "name": "Drive Mode",
        "description": "Active drive profile code (vehicle specific)",
        "icon": "mdi:car-shift-pattern",
        "category": CATEGORY_DIAGNOSTIC,
    },
    "v.e.headlights": {
        "name": "Headlights",
        "description": "Headlights on state",
        "icon": "mdi:car-light-high",
        "device_class": BinarySensorDeviceClass.LIGHT,
        "category": CATEGORY_DIAGNOSTIC,
    },
    "v.e.on": {
        "name": "Vehicle On",
        "description": "Vehicle is in ignition state (drivable)",
        "icon": "mdi:power",
        "device_class": BinarySensorDeviceClass.POWER,
        "category": CATEGORY_DIAGNOSTIC,
    },
    "v.e.serv.range": {
        "name": "Service Distance",
        "description": "Distance to next scheduled maintenance/service",
        "icon": "mdi:wrench-clock",
        "device_class": SensorDeviceClass.DISTANCE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfLength.KILOMETERS,
        "category": CATEGORY_DIAGNOSTIC,
    },
    "v.e.serv.time": {
        "name": "Service Date",
        "description": "Time of next scheduled maintenance/service",
        "icon": "mdi:wrench-clock",
        "device_class": SensorDeviceClass.TIMESTAMP,
        "category": CATEGORY_DIAGNOSTIC,
    },
    "v.e.valet": {
        "name": "Valet Mode",
        "description": "Valet mode engaged state",
        "icon": "mdi:account-key",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "category": CATEGORY_DIAGNOSTIC,
    },
}
