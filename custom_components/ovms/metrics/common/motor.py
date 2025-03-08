"""Motor metrics for OVMS integration."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfPower,
)

# Motor metrics
MOTOR_METRICS = {
    "v.i.temp": {
        "name": "Inverter Temperature",
        "description": "Inverter temperature",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "category": "motor",
    },
    "v.i.power": {
        "name": "Inverter Power",
        "description": "Momentary inverter motor power (output=positive)",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.KILO_WATT,
        "category": "motor",
    },
    "v.i.efficiency": {
        "name": "Inverter Efficiency",
        "description": "Momentary inverter efficiency",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER_FACTOR,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": "motor",
    },
    "v.m.rpm": {
        "name": "Motor RPM",
        "description": "Motor speed (RPM)",
        "icon": "mdi:rotate-right",
        "category": "motor",
    },
    "v.m.temp": {
        "name": "Motor Temperature",
        "description": "Motor temperature",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "category": "motor",
    },
}
