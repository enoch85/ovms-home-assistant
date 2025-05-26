"""Diagnostic metrics for OVMS integration."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
)
from homeassistant.const import (
    UnitOfLength,
)
from homeassistant.const import EntityCategory  # noqa: F401

# Diagnostic metrics
DIAGNOSTIC_METRICS = {
    "v.e.alarm": {
        "name": "Alarm",
        "description": "Alarm sounding state",
        "icon": "mdi:bell-ring",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "category": "diagnostic",
    },
    "v.e.aux12v": {
        "name": "12V System",
        "description": "12V auxiliary system state (base system awake)",
        "icon": "mdi:power-plug",
        "device_class": BinarySensorDeviceClass.POWER,
        "category": "diagnostic",
    },
    "v.e.awake": {
        "name": "Vehicle Awake",
        "description": "Vehicle is fully awake (switched on by the user)",
        "icon": "mdi:power",
        "device_class": BinarySensorDeviceClass.POWER,
        "category": "diagnostic",
    },
    "v.e.c.config": {
        "name": "ECU Configuration Mode",
        "description": "ECU/controller in configuration state",
        "icon": "mdi:wrench",
        "category": "diagnostic",
        "device_class": BinarySensorDeviceClass.UPDATE,
    },
    "v.e.c.login": {
        "name": "ECU Login Status",
        "description": "Module logged in at ECU/controller",
        "icon": "mdi:login",
        "category": "diagnostic",
        "device_class": BinarySensorDeviceClass.CONNECTIVITY,
    },
    "v.e.charging12v": {
        "name": "12V Battery Charging",
        "description": "12V battery charging state",
        "icon": "mdi:battery-charging",
        "device_class": BinarySensorDeviceClass.BATTERY_CHARGING,
        "category": "diagnostic",
    },
    "v.e.drivemode": {
        "name": "Drive Mode",
        "description": "Active drive profile code (vehicle specific)",
        "icon": "mdi:car-shift-pattern",
        "category": "diagnostic",
    },
    "v.e.gear": {
        "name": "Gear",
        "description": "Gear/direction; negative=reverse, 0=neutral",
        "icon": "mdi:car-shift-pattern",
        "category": "diagnostic",
    },
    "v.e.handbrake": {
        "name": "Handbrake",
        "description": "Handbrake engaged state",
        "icon": "mdi:car-brake-parking",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "category": "diagnostic",
    },
    "v.e.headlights": {
        "name": "Headlights",
        "description": "Headlights on state",
        "icon": "mdi:car-light-high",
        "device_class": BinarySensorDeviceClass.LIGHT,
        "category": "diagnostic",
    },
    "v.e.on": {
        "name": "Vehicle On",
        "description": "Vehicle is in ignition state (drivable)",
        "icon": "mdi:power",
        "device_class": BinarySensorDeviceClass.POWER,
        "category": "diagnostic",
    },
    "v.e.serv.range": {
        "name": "Service Distance",
        "description": "Distance to next scheduled maintenance/service",
        "icon": "mdi:wrench-clock",
        "device_class": SensorDeviceClass.DISTANCE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfLength.KILOMETERS,
        "category": "diagnostic",
    },
    "v.e.serv.time": {
        "name": "Service Date",
        "description": "Time of next scheduled maintenance/service",
        "icon": "mdi:wrench-clock",
        "device_class": SensorDeviceClass.TIMESTAMP,
        "category": "diagnostic",
    },
    "v.e.valet": {
        "name": "Valet Mode",
        "description": "Valet mode engaged state",
        "icon": "mdi:account-key",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "category": "diagnostic",
    },
}
