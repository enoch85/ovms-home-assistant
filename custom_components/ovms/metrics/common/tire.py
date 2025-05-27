"""Tire metrics for OVMS integration."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfPressure,
    UnitOfTemperature,
)

# Tire position mapping based on OVMS standard: LF, RF, LR, RR
TIRE_POSITIONS = {
    0: ("front_left", "FL"),
    1: ("front_right", "FR"), 
    2: ("rear_left", "LR"),
    3: ("rear_right", "RR")
}

# Tire metrics
TIRE_METRICS = {
    "v.t.alert": {
        "name": "Tire Alerts",
        "description": "TPMS tire alert levels [0=normal, 1=warning, 2=alert]",
        "icon": "mdi:car-tire-alert",
        "category": "tire",
    },
    "v.t.health": {
        "name": "Tire Health",
        "description": "TPMS tire health states",
        "icon": "mdi:car-tire-alert",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": "tire",
        "has_cell_data": True,
    },
    "v.t.pressure": {
        "name": "Tire Pressure",
        "description": "TPMS tire pressures",
        "icon": "mdi:gauge",
        "device_class": SensorDeviceClass.PRESSURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPressure.KPA,
        "category": "tire",
        "has_cell_data": True,
    },
    "v.t.temp": {
        "name": "Tire Temperature",
        "description": "TPMS tire temperatures",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "category": "tire",
        "has_cell_data": True,
    },
    "v.t.diff": {
        "name": "Tire Pressure Difference",
        "description": "Difference in tire pressure values",
        "icon": "mdi:car-tire-alert",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPressure.KPA,
        "category": "tire",
        "has_cell_data": True,
    },
}
