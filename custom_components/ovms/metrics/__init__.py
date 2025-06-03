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
    EntityCategory,
)

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
from .vehicles import VW_EUP_METRICS, SMART_FORTWO_METRICS, MG_ZS_EV_METRICS, NISSAN_LEAF_METRICS, RENAULT_TWIZY_METRICS

# Import patterns and utils
from .patterns import TOPIC_PATTERNS
from .utils import (
    get_metric_by_path,
    get_metric_by_pattern,
    determine_category_from_topic,
    create_friendly_name,
)

# Import category constants from const.py to maintain single source of truth
from ..const import (
    CATEGORY_BATTERY,
    CATEGORY_CHARGING,
    CATEGORY_CLIMATE,
    CATEGORY_DOOR,
    CATEGORY_LOCATION,
    CATEGORY_MOTOR,
    CATEGORY_TRIP,
    CATEGORY_DEVICE,
    CATEGORY_DIAGNOSTIC,
    CATEGORY_POWER,
    CATEGORY_NETWORK,
    CATEGORY_SYSTEM,
    CATEGORY_TIRE,
    CATEGORY_VW_EUP,
    CATEGORY_SMART_FORTWO,
    CATEGORY_MG_ZS_EV,
    CATEGORY_NISSAN_LEAF,
    CATEGORY_RENAULT_TWIZY,
)

# Custom unit constants
UNIT_AMPERE_HOUR = "Ah"

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
    **RENAULT_TWIZY_METRICS,
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
    CATEGORY_RENAULT_TWIZY: [
        k for k, v in METRIC_DEFINITIONS.items() if v.get("category") == CATEGORY_RENAULT_TWIZY
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
    # Battery metrics
    "v.b": CATEGORY_BATTERY,
    
    # Charging metrics
    "v.c": CATEGORY_CHARGING,
    
    # Door metrics
    "v.d": CATEGORY_DOOR,
    
    # Environment metrics - split climate from diagnostic
    "v.e.cabin": CATEGORY_CLIMATE,
    "v.e.heating": CATEGORY_CLIMATE,
    "v.e.cooling": CATEGORY_CLIMATE,
    "v.e.hvac": CATEGORY_CLIMATE,
    "v.e.temp": CATEGORY_CLIMATE,
    "v.e": CATEGORY_DIAGNOSTIC,  # Fallback for other environment metrics
    
    # Power metrics
    "v.g": CATEGORY_POWER,
    
    # Inverter/Motor metrics - split by type
    "v.i.temp": CATEGORY_MOTOR,  # Motor temperatures
    "v.i.rpm": CATEGORY_MOTOR,   # Motor RPM
    "v.i.pwr": CATEGORY_MOTOR,   # Motor power
    "v.i": CATEGORY_DIAGNOSTIC,  # General inverter diagnostics
    
    # Motor metrics
    "v.m": CATEGORY_MOTOR,
    
    # Position/Location metrics - specific GPS mappings
    "v.p.altitude": CATEGORY_LOCATION,
    "v.p.direction": CATEGORY_LOCATION,
    "v.p.gpshdop": CATEGORY_LOCATION,
    "v.p.gpslock": CATEGORY_LOCATION,
    "v.p.gpsmode": CATEGORY_LOCATION,
    "v.p.gpssq": CATEGORY_LOCATION,
    "v.p.gpsspeed": CATEGORY_LOCATION,
    "v.p.gpstime": CATEGORY_LOCATION,
    "v.p.latitude": CATEGORY_LOCATION,
    "v.p.longitude": CATEGORY_LOCATION,
    "v.p.location": CATEGORY_LOCATION,
    "v.p.satcount": CATEGORY_LOCATION,
    "v.p.valet.latitude": CATEGORY_LOCATION,
    "v.p.valet.longitude": CATEGORY_LOCATION,
    # Trip metrics from v.p namespace
    "v.p.acceleration": CATEGORY_TRIP,
    "v.p.deceleration": CATEGORY_TRIP,
    "v.p.odometer": CATEGORY_TRIP,
    "v.p.speed": CATEGORY_TRIP,
    "v.p.trip": CATEGORY_TRIP,
    
    # Tire metrics
    "v.t": CATEGORY_TIRE,
    
    # Network metrics - more specific mappings
    "m.net.provider": CATEGORY_NETWORK,
    "m.net.sq": CATEGORY_NETWORK,
    "m.net.type": CATEGORY_NETWORK,
    "m.net": CATEGORY_NETWORK,
    
    # System metrics - more specific mappings
    "m.freeram": CATEGORY_SYSTEM,
    "m.hardware": CATEGORY_SYSTEM,
    "m.serial": CATEGORY_SYSTEM,
    "m.version": CATEGORY_SYSTEM,
    "m": CATEGORY_SYSTEM,  # Fallback for other module metrics
    
    # Server metrics
    "s.v2": CATEGORY_SYSTEM,
    "s.v3": CATEGORY_SYSTEM,
    "s": CATEGORY_SYSTEM,  # Fallback for other server metrics
    
    # Vehicle-specific metrics
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
    "xrt.b": CATEGORY_RENAULT_TWIZY,
    "xrt.bms": CATEGORY_RENAULT_TWIZY,
    "xrt.cfg": CATEGORY_RENAULT_TWIZY,
    "xrt.i": CATEGORY_RENAULT_TWIZY,
    "xrt.m": CATEGORY_RENAULT_TWIZY,
    "xrt.p": CATEGORY_RENAULT_TWIZY,
    "xrt.s": CATEGORY_RENAULT_TWIZY,
    "xrt.v": CATEGORY_RENAULT_TWIZY,
}
