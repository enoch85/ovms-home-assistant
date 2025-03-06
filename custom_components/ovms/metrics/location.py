"""Location metrics for OVMS integration."""
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfLength,
    UnitOfSpeed,
)

# Category
CATEGORY_LOCATION = "location"
CATEGORY_TRIP = "trip"

# Location metrics
LOCATION_METRICS = {
    "v.p.acceleration": {
        "name": "Acceleration",
        "description": "Vehicle acceleration",
        "icon": "mdi:speedometer",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "m/s²",
        "category": CATEGORY_TRIP,
    },
    "v.p.altitude": {
        "name": "Altitude",
        "description": "GPS altitude",
        "icon": "mdi:elevation-rise",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfLength.METERS,
        "category": CATEGORY_LOCATION,
    },
    "v.p.direction": {
        "name": "Direction",
        "description": "GPS direction",
        "icon": "mdi:compass",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "°",
        "category": CATEGORY_LOCATION,
    },
    "v.p.gpshdop": {
        "name": "GPS HDOP",
        "description": "GPS horizontal dilution of precision (smaller=better)",
        "icon": "mdi:crosshairs-gps",
        "state_class": SensorStateClass.MEASUREMENT,
        "category": CATEGORY_LOCATION,
    },
    "v.p.gpslock": {
        "name": "GPS Lock",
        "description": "GPS satellite lock",
        "icon": "mdi:crosshairs-gps",
        "device_class": BinarySensorDeviceClass.CONNECTIVITY,
        "category": CATEGORY_LOCATION,
    },
    "v.p.gpsmode": {
        "name": "GPS Mode",
        "description": "<GPS><GLONASS>; N/A/D/E (None/Autonomous/Differential/Estimated)",
        "icon": "mdi:crosshairs-gps",
        "category": CATEGORY_LOCATION,
    },
    "v.p.gpssq": {
        "name": "GPS Signal Quality",
        "description": "GPS signal quality [%]",
        "icon": "mdi:signal",
        "device_class": SensorDeviceClass.SIGNAL_STRENGTH,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": CATEGORY_LOCATION,
    },
    "v.p.gpsspeed": {
        "name": "GPS Speed",
        "description": "GPS speed over ground",
        "icon": "mdi:speedometer",
        "device_class": SensorDeviceClass.SPEED,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfSpeed.KILOMETERS_PER_HOUR,
        "category": CATEGORY_LOCATION,
    },
    "v.p.gpstime": {
        "name": "GPS Time",
        "description": "Time of GPS coordinates",
        "icon": "mdi:clock",
        "device_class": SensorDeviceClass.TIMESTAMP,
        "category": CATEGORY_LOCATION,
    },
    "v.p.latitude": {
        "name": "Latitude",
        "description": "GPS latitude",
        "icon": "mdi:map-marker",
        "state_class": SensorStateClass.MEASUREMENT,
        "category": CATEGORY_LOCATION,
    },
    "v.p.location": {
        "name": "Location Name",
        "description": "Name of current location if defined",
        "icon": "mdi:map-marker",
        "category": CATEGORY_LOCATION,
    },
    "v.p.longitude": {
        "name": "Longitude",
        "description": "GPS longitude",
        "icon": "mdi:map-marker",
        "state_class": SensorStateClass.MEASUREMENT,
        "category": CATEGORY_LOCATION,
    },
    "v.p.odometer": {
        "name": "Odometer",
        "description": "Vehicle odometer",
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.DISTANCE,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfLength.KILOMETERS,
        "category": CATEGORY_TRIP,
    },
    "v.p.satcount": {
        "name": "GPS Satellites",
        "description": "GPS satellite count in view",
        "icon": "mdi:satellite-variant",
        "state_class": SensorStateClass.MEASUREMENT,
        "category": CATEGORY_LOCATION,
    },
    "v.p.speed": {
        "name": "Vehicle Speed",
        "description": "Vehicle speed",
        "icon": "mdi:speedometer",
        "device_class": SensorDeviceClass.SPEED,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfSpeed.KILOMETERS_PER_HOUR,
        "category": CATEGORY_TRIP,
    },
    "v.p.trip": {
        "name": "Trip Odometer",
        "description": "Trip odometer",
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.DISTANCE,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfLength.KILOMETERS,
        "category": CATEGORY_TRIP,
    },
    "v.e.drivetime": {
        "name": "Drive Time",
        "description": "Seconds driving (turned on)",
        "icon": "mdi:timer",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "s",
        "category": CATEGORY_TRIP,
    },
    "v.e.parktime": {
        "name": "Park Time",
        "description": "Seconds parking (turned off)",
        "icon": "mdi:timer",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "s",
        "category": CATEGORY_TRIP,
    },
}
