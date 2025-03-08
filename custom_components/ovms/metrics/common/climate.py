"""Climate metrics for OVMS integration."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTemperature,
)

# Climate metrics
CLIMATE_METRICS = {
    "v.e.cabintemp": {
        "name": "Cabin Temperature",
        "description": "Cabin temperature",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "category": "climate",
    },
    "v.e.cabinfan": {
        "name": "Cabin Fan",
        "description": "Cabin fan speed",
        "icon": "mdi:fan",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": "climate",
    },
    "v.e.cabinsetpoint": {
        "name": "Cabin Temperature Setpoint",
        "description": "Cabin set point",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "category": "climate",
    },
    "v.e.cabinintake": {
        "name": "Cabin Air Intake",
        "description": "Cabin intake type (fresh, recirc, etc)",
        "icon": "mdi:air-filter",
        "category": "climate",
    },
    "v.e.cabinvent": {
        "name": "Cabin Air Vents",
        "description": "Cabin vent type (comma-separated list of feet, face, screen, etc)",
        "icon": "mdi:air-conditioner",
        "category": "climate",
    },
    "v.e.cooling": {
        "name": "Cooling Active",
        "description": "Cooling system active state",
        "icon": "mdi:snowflake",
        "device_class": BinarySensorDeviceClass.COLD,
        "category": "climate",
    },
    "v.e.heating": {
        "name": "Heating Active",
        "description": "Heating system active state",
        "icon": "mdi:fire",
        "device_class": BinarySensorDeviceClass.HEAT,
        "category": "climate",
    },
    "v.e.hvac": {
        "name": "HVAC Active",
        "description": "HVAC active state",
        "icon": "mdi:air-conditioner",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "category": "climate",
    },
    "v.e.temp": {
        "name": "Ambient Temperature",
        "description": "Ambient temperature",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "category": "climate",
    },
}
