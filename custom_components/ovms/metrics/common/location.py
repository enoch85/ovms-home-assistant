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

# Location metrics
LOCATION_METRICS = {
    "v.p.altitude": {
        "name": "Altitude",
        "description": "GPS altitude",
        "icon": "mdi:elevation-rise",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfLength.METERS,
        "category": "location",
    },
    "v.p.direction": {
        "name": "Direction",
        "description": "GPS direction",
        "icon": "mdi:compass",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "°",
        "category": "location",
    },
    "v.p.gpshdop": {
        "name": "GPS HDOP",
        "description": "GPS horizontal dilution of precision (smaller=better)",
        "icon": "mdi:crosshairs-gps",
        "state_class": SensorStateClass.MEASUREMENT,
        "category": "location",
    },
    "v.p.gpslock": {
        "name": "GPS Lock",
        "description": "GPS satellite lock",
        "icon": "mdi:crosshairs-gps",
        "device_class": BinarySensorDeviceClass.CONNECTIVITY,
        "category": "location",
    },
    "v.p.gpsmode": {
        "name": "GPS Mode",
        "description": "<GPS><GLONASS>; N/A/D/E (None/Autonomous/Differential/Estimated)",
        "icon": "mdi:crosshairs-gps",
        "category": "location",
        "device_class": None,  # Explicitly not numeric
        "state_class": None,
    },
    "v.p.gpssq": {
        "name": "GPS Signal Quality",
        "description": "GPS signal quality",
        "icon": "mdi:signal",
        "device_class": SensorDeviceClass.SIGNAL_STRENGTH,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "dBm",
        "category": "location",
    },
    "v.p.gpsspeed": {
        "name": "GPS Speed",
        "description": "GPS speed over ground",
        "icon": "mdi:speedometer",
        "device_class": SensorDeviceClass.SPEED,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfSpeed.KILOMETERS_PER_HOUR,
        "category": "location",
    },
    "v.p.gpstime": {
        "name": "GPS Time",
        "description": "Time of GPS coordinates",
        "icon": "mdi:clock",
        "device_class": SensorDeviceClass.TIMESTAMP,
        "category": "location",
        "state_class": None,  # Timestamps don't have a state class
    },
    "v.p.latitude": {
        "name": "Latitude",
        "description": "GPS latitude",
        "icon": "mdi:map-marker",
        "state_class": SensorStateClass.MEASUREMENT,
        "category": "location",
    },
    "v.p.location": {
        "name": "Location Name",
        "description": "Name of current location if defined",
        "icon": "mdi:map-marker",
        "category": "location",
        "device_class": None,  # Explicitly not numeric
        "state_class": None,
    },
    "v.p.longitude": {
        "name": "Longitude",
        "description": "GPS longitude",
        "icon": "mdi:map-marker",
        "state_class": SensorStateClass.MEASUREMENT,
        "category": "location",
    },
    "v.p.satcount": {
        "name": "GPS Satellites",
        "description": "GPS satellite count in view",
        "icon": "mdi:satellite-variant",
        "state_class": SensorStateClass.MEASUREMENT,
        "category": "location",
    },
    "v.p.valet.latitude": {
        "name": "Valet Mode Last Latitude",
        "description": "Last known latitude position in valet mode",
        "icon": "mdi:map-marker",
        "state_class": SensorStateClass.MEASUREMENT,
        "category": "location",
    },
    "v.p.valet.longitude": {
        "name": "Valet Mode Last Longitude",
        "description": "Last known longitude position in valet mode",
        "icon": "mdi:map-marker",
        "state_class": SensorStateClass.MEASUREMENT,
        "category": "location",
    },
}
