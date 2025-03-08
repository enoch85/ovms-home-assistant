"""Trip metrics for OVMS integration."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfLength,
    UnitOfSpeed,
    UnitOfTime,
)

# Trip metrics
TRIP_METRICS = {
    "v.e.drivetime": {
        "name": "Drive Time",
        "description": "Seconds driving (turned on)",
        "icon": "mdi:timer",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTime.SECONDS,
        "category": "trip",
    },
    "v.e.parktime": {
        "name": "Park Time",
        "description": "Seconds parking (turned off)",
        "icon": "mdi:timer",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTime.SECONDS,
        "category": "trip",
    },
    "v.p.acceleration": {
        "name": "Acceleration",
        "description": "Vehicle acceleration",
        "icon": "mdi:speedometer",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "m/s²",
        "category": "trip",
    },
    "v.p.odometer": {
        "name": "Odometer",
        "description": "Vehicle odometer",
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.DISTANCE,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfLength.KILOMETERS,
        "category": "trip",
    },
    "v.p.speed": {
        "name": "Vehicle Speed",
        "description": "Vehicle speed",
        "icon": "mdi:speedometer",
        "device_class": SensorDeviceClass.SPEED,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfSpeed.KILOMETERS_PER_HOUR,
        "category": "trip",
    },
    "v.p.trip": {
        "name": "Trip Odometer",
        "description": "Trip odometer",
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.DISTANCE,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfLength.KILOMETERS,
        "category": "trip",
    },
    "v.p.valet.distance": {
        "name": "Valet Mode Distance",
        "description": "Distance traveled in valet mode",
        "icon": "mdi:map-marker-distance",
        "device_class": SensorDeviceClass.DISTANCE,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfLength.KILOMETERS,
        "category": "trip",
    },
    "v.e.throttle": {
        "name": "Accelerator Pedal",
        "description": "Drive pedal state [%]",
        "icon": "mdi:gas-station",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": "trip",
    },
    "v.e.footbrake": {
        "name": "Brake Pedal",
        "description": "Brake pedal state [%]",
        "icon": "mdi:car-brake-alert",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": "trip",
    },
}
