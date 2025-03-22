"""Metrics definitions for OVMS integration."""

# Import constants
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfPower,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfFrequency,
)
from homeassistant.helpers.entity import EntityCategory

# Import from common metrics
from .common import (
    BATTERY_METRICS,
    CHARGING_METRICS,
    CLIMATE_METRICS,
    DOOR_METRICS,
    LOCATION_METRICS,
    MOTOR_METRICS,
    TRIP_METRICS,
    DEVICE_METRICS,
    DIAGNOSTIC_METRICS,
    POWER_METRICS,
    NETWORK_METRICS,
    SYSTEM_METRICS,
    TIRE_METRICS,
)

# Import vehicle-specific metrics
from .vehicles import VW_EUP_METRICS, SMART_FORTWO_METRICS, MG_ZS_EV_METRICS, NISSAN_LEAF_METRICS

# Import patterns and utils
from .patterns import TOPIC_PATTERNS
from .utils import (
    get_metric_by_path,
    get_metric_by_pattern,
    determine_category_from_topic,
    create_friendly_name,
)

# Custom unit constants
UNIT_AMPERE_HOUR = "Ah"

# Categories of metrics
CATEGORY_BATTERY = "battery"
CATEGORY_CHARGING = "charging"
CATEGORY_CLIMATE = "climate"
CATEGORY_DOOR = "door"
CATEGORY_LOCATION = "location"
CATEGORY_MOTOR = "motor"
CATEGORY_TRIP = "trip"
CATEGORY_DEVICE = "device"
CATEGORY_DIAGNOSTIC = "diagnostic"
CATEGORY_POWER = "power"
CATEGORY_NETWORK = "network"
CATEGORY_SYSTEM = "system"
CATEGORY_TIRE = "tire"
CATEGORY_VW_EUP = "vw_eup"
CATEGORY_SMART_FORTWO = "smart_fortwo"
CATEGORY_MG_ZS_EV = "mg_zs_ev"
CATEGORY_NISSAN_LEAF = "nissan_leaf"

# Combine all metrics into the master dictionary
METRIC_DEFINITIONS = {
    **BATTERY_METRICS,
    **CHARGING_METRICS,
    **CLIMATE_METRICS,
    **DOOR_METRICS,
    **LOCATION_METRICS,
    **MOTOR_METRICS,
    **TRIP_METRICS,
    **DEVICE_METRICS,
    **DIAGNOSTIC_METRICS,
    **POWER_METRICS,
    **NETWORK_METRICS,
    **SYSTEM_METRICS,
    **TIRE_METRICS,
    **VW_EUP_METRICS,
    **SMART_FORTWO_METRICS,
    **MG_ZS_EV_METRICS,
    **NISSAN_LEAF_METRICS,
}

# Group metrics by categories
METRIC_CATEGORIES = {
    CATEGORY_BATTERY: [
        k
        for k, v in METRIC_DEFINITIONS.items()
        if v.get("category") == CATEGORY_BATTERY
    ],
    CATEGORY_CHARGING: [
        k
        for k, v in METRIC_DEFINITIONS.items()
        if v.get("category") == CATEGORY_CHARGING
    ],
    CATEGORY_CLIMATE: [
        k
        for k, v in METRIC_DEFINITIONS.items()
        if v.get("category") == CATEGORY_CLIMATE
    ],
    CATEGORY_DOOR: [
        k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_DOOR
    ],
    CATEGORY_LOCATION: [
        k
        for k, v in METRIC_DEFINITIONS.items()
        if v.get("category") == CATEGORY_LOCATION
    ],
    CATEGORY_MOTOR: [
        k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_MOTOR
    ],
    CATEGORY_TRIP: [
        k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_TRIP
    ],
    CATEGORY_DEVICE: [
        k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_DEVICE
    ],
    CATEGORY_DIAGNOSTIC: [
        k
        for k, v in METRIC_DEFINITIONS.items()
        if v.get("category") == CATEGORY_DIAGNOSTIC
    ],
    CATEGORY_POWER: [
        k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_POWER
    ],
    CATEGORY_NETWORK: [
        k
        for k, v in METRIC_DEFINITIONS.items()
        if v.get("category") == CATEGORY_NETWORK
    ],
    CATEGORY_SYSTEM: [
        k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_SYSTEM
    ],
    CATEGORY_TIRE: [
        k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_TIRE
    ],
    CATEGORY_VW_EUP: [
        k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_VW_EUP
    ],
    CATEGORY_SMART_FORTWO: [
        k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_SMART_FORTWO
    ],
    CATEGORY_MG_ZS_EV: [
        k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_MG_ZS_EV
    ],
    CATEGORY_NISSAN_LEAF: [
        k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_NISSAN_LEAF
    ],
}

# Binary metrics that should be boolean - includes only actual binary metrics
BINARY_METRICS = [
    k for k, v in METRIC_DEFINITIONS.items()
    if v.get("device_class") in [
        BinarySensorDeviceClass.DOOR,
        BinarySensorDeviceClass.LOCK,
        BinarySensorDeviceClass.BATTERY_CHARGING,
        BinarySensorDeviceClass.CONNECTIVITY,
        BinarySensorDeviceClass.LIGHT,
        BinarySensorDeviceClass.COLD,
        BinarySensorDeviceClass.HEAT,
        BinarySensorDeviceClass.PROBLEM,
        BinarySensorDeviceClass.RUNNING,
        BinarySensorDeviceClass.UPDATE,
    ] or k.endswith((".on", ".charging", ".alarm", ".alert", ".locked", ".hvac"))
]

# Prefix patterns to detect entity categories
PREFIX_CATEGORIES = {
    "v.b": CATEGORY_BATTERY,
    "v.c": CATEGORY_CHARGING,
    "v.d": CATEGORY_DOOR,
    "v.e.cabin": CATEGORY_CLIMATE,
    "v.e": CATEGORY_DIAGNOSTIC,
    "v.g": CATEGORY_POWER,
    "v.i": CATEGORY_MOTOR,
    "v.m": CATEGORY_MOTOR,
    "v.p": CATEGORY_LOCATION,
    "v.t": CATEGORY_TIRE,
    "m.net": CATEGORY_NETWORK,
    "m": CATEGORY_SYSTEM,
    "s": CATEGORY_SYSTEM,
    "xvu.b": CATEGORY_VW_EUP,
    "xvu.c": CATEGORY_VW_EUP,
    "xvu.e": CATEGORY_VW_EUP,
    "xvu.m": CATEGORY_VW_EUP,
    "xvu.v": CATEGORY_VW_EUP,
    "xsq.bms": CATEGORY_SMART_FORTWO,
    "xsq.booster": CATEGORY_SMART_FORTWO,
    "xsq.evc": CATEGORY_SMART_FORTWO,
    "xsq.obl": CATEGORY_SMART_FORTWO,
    "xsq.ocs": CATEGORY_SMART_FORTWO,
    "xsq.odometer": CATEGORY_SMART_FORTWO,
    "xsq.use": CATEGORY_SMART_FORTWO,
    "xsq.v": CATEGORY_SMART_FORTWO,
    "xmg.b": CATEGORY_MG_ZS_EV,
    "xmg.c": CATEGORY_MG_ZS_EV,
    "xmg.p": CATEGORY_MG_ZS_EV,
    "xmg.v": CATEGORY_MG_ZS_EV,
    "xmg.state": CATEGORY_MG_ZS_EV,
    "xmg.task": CATEGORY_MG_ZS_EV,
    "xmg.enable": CATEGORY_MG_ZS_EV,
    "xmg.auth": CATEGORY_MG_ZS_EV,
    "xnl.bms": CATEGORY_NISSAN_LEAF,
    "xnl.cc": CATEGORY_NISSAN_LEAF,
    "xnl.v.b": CATEGORY_NISSAN_LEAF,
    "xnl.v.c": CATEGORY_NISSAN_LEAF,
    "xnl.v.e": CATEGORY_NISSAN_LEAF,
}
