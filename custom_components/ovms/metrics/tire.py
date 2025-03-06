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

# Category
CATEGORY_TIRE = "tire"

# Tire metrics
TIRE_METRICS = {
    "v.t.alert": {
        "name": "Tire Alerts",
        "description": "TPMS tire alert levels [0=normal, 1=warning, 2=alert]",
        "icon": "mdi:car-tire-alert",
        "category": CATEGORY_TIRE,
    },
    "v.t.health": {
        "name": "Tire Health",
        "description": "TPMS tire health states",
        "icon": "mdi:car-tire-alert",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": CATEGORY_TIRE,
    },
    "v.t.pressure": {
        "name": "Tire Pressure",
        "description": "TPMS tire pressures",
        "icon": "mdi:gauge",
        "device_class": SensorDeviceClass.PRESSURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPressure.KPA,
        "category": CATEGORY_TIRE,
    },
    "v.t.temp": {
        "name": "Tire Temperature",
        "description": "TPMS tire temperatures",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "category": CATEGORY_TIRE,
    },
}
