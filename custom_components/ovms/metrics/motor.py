"""Motor and inverter metrics for OVMS integration."""
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfPower,
    UnitOfTemperature,
)

# Category
CATEGORY_MOTOR = "motor"

# Motor metrics
MOTOR_METRICS = {
    "v.i.temp": {
        "name": "Inverter Temperature",
        "description": "Inverter temperature",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "category": CATEGORY_MOTOR,
    },
    "v.i.power": {
        "name": "Inverter Power",
        "description": "Momentary inverter motor power (output=positive)",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.KILO_WATT,
        "category": CATEGORY_MOTOR,
    },
    "v.i.efficiency": {
        "name": "Inverter Efficiency",
        "description": "Momentary inverter efficiency",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER_FACTOR,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": CATEGORY_MOTOR,
    },
    "v.m.rpm": {
        "name": "Motor RPM",
        "description": "Motor speed (RPM)",
        "icon": "mdi:rotate-right",
        "category": CATEGORY_MOTOR,
    },
    "v.m.temp": {
        "name": "Motor Temperature",
        "description": "Motor temperature",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "category": CATEGORY_MOTOR,
    },
    "v.e.throttle": {
        "name": "Accelerator Pedal",
        "description": "Drive pedal state [%]",
        "icon": "mdi:gas-station",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": CATEGORY_MOTOR,
    },
    "v.e.footbrake": {
        "name": "Brake Pedal",
        "description": "Brake pedal state [%]",
        "icon": "mdi:car-brake-alert",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": CATEGORY_MOTOR,
    },
    "v.e.handbrake": {
        "name": "Handbrake",
        "description": "Handbrake engaged state",
        "icon": "mdi:car-brake-parking",
        "device_class": "problem",
        "category": CATEGORY_MOTOR,
    },
    "v.e.gear": {
        "name": "Gear",
        "description": "Gear/direction; negative=reverse, 0=neutral",
        "icon": "mdi:car-shift-pattern",
        "category": CATEGORY_MOTOR,
    },
    "v.e.regenbrake": {
        "name": "Regenerative Braking",
        "description": "Regenerative braking active state",
        "icon": "mdi:battery-charging",
        "device_class": "running",
        "category": CATEGORY_MOTOR,
    },
}
