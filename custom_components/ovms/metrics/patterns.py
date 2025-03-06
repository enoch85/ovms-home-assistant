"""Pattern matching definitions for OVMS metrics."""
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
)
from homeassistant.helpers.entity import EntityCategory

# Simplified mapping for lookup by keyword/pattern
TOPIC_PATTERNS = {
    "soc": {
        "name": "Battery State of Charge",
        "icon": "mdi:battery",
        "device_class": SensorDeviceClass.BATTERY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": "battery",
    },
    "range": {
        "name": "Range",
        "icon": "mdi:map-marker-distance",
        "device_class": SensorDeviceClass.DISTANCE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfLength.KILOMETERS,
        "category": "battery",
    },
    "temp": {
        "name": "Temperature",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "category": "climate",
    },
    "voltage": {
        "name": "Voltage",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "category": "battery",
    },
    "current": {
        "name": "Current",
        "icon": "mdi:current-ac",
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricCurrent.AMPERE,
        "category": "battery",
    },
    "power": {
        "name": "Power",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
        "category": "power",
    },
    "energy": {
        "name": "Energy",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "category": "battery",
    },
    "speed": {
        "name": "Speed",
        "icon": "mdi:speedometer",
        "device_class": SensorDeviceClass.SPEED,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfSpeed.KILOMETERS_PER_HOUR,
        "category": "trip",
    },
    "odometer": {
        "name": "Odometer",
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.DISTANCE,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfLength.KILOMETERS,
        "category": "trip",
    },
    "pressure": {
        "name": "Pressure",
        "icon": "mdi:gauge",
        "device_class": SensorDeviceClass.PRESSURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPressure.KPA,
        "category": "tire",
    },
    "signal": {
        "name": "Signal Strength",
        "icon": "mdi:signal",
        "device_class": SensorDeviceClass.SIGNAL_STRENGTH,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "dBm",
        "category": "network",
    },
    "door": {
        "name": "Door",
        "icon": "mdi:car-door",
        "device_class": BinarySensorDeviceClass.DOOR,
        "category": "door",
    },
    "lock": {
        "name": "Lock",
        "icon": "mdi:lock",
        "device_class": BinarySensorDeviceClass.LOCK,
        "category": "door",
    },
    "charging": {
        "name": "Charging",
        "icon": "mdi:battery-charging",
        "device_class": BinarySensorDeviceClass.BATTERY_CHARGING,
        "category": "charging",
    },
    "climate": {
        "name": "Climate Control",
        "icon": "mdi:air-conditioner",
        "category": "climate",
    },
    "fan": {
        "name": "Fan",
        "icon": "mdi:fan",
        "category": "climate",
    },
    "trunk": {
        "name": "Trunk",
        "icon": "mdi:car-back",
        "device_class": BinarySensorDeviceClass.DOOR,
        "category": "door",
    },
    "hood": {
        "name": "Hood",
        "icon": "mdi:car-lifted-pickup",
        "device_class": BinarySensorDeviceClass.DOOR,
        "category": "door",
    },
    "timer": {
        "name": "Timer",
        "icon": "mdi:timer",
        "device_class": SensorDeviceClass.DURATION,
        "category": "system",
    },
    "version": {
        "name": "Version",
        "icon": "mdi:package-up",
        "category": "system",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "status": {
        "name": "Status",
        "icon": "mdi:information-outline",
        "category": "system",
    },
    "alert": {
        "name": "Alert",
        "icon": "mdi:alert",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "category": "diagnostic",
    }
}
