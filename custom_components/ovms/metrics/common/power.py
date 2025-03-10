"""Power metrics for OVMS integration."""

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
    UnitOfTemperature,
    UnitOfTime,
)

# Power metrics
POWER_METRICS = {
    # DC/DC converter metrics
    "v.c.12v.current": {
        "name": "DC-DC Converter Current",
        "description": "Output current of DC/DC-converter",
        "icon": "mdi:current-ac",
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricCurrent.AMPERE,
        "category": "power",
    },
    "v.c.12v.power": {
        "name": "DC-DC Converter Power",
        "description": "Output power of DC/DC-converter",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
        "category": "power",
    },
    "v.c.12v.temp": {
        "name": "DC-DC Converter Temperature",
        "description": "Temperature of DC/DC-converter",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "category": "power",
    },
    "v.c.12v.voltage": {
        "name": "DC-DC Converter Voltage",
        "description": "Output voltage of DC/DC-converter",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "category": "power",
    },

    # Generator metrics (power output)
    "v.g.generating": {
        "name": "Generating",
        "description": "Currently delivering power state",
        "icon": "mdi:flash",
        "device_class": BinarySensorDeviceClass.POWER,
        "category": "power",
    },
    "v.g.climit": {
        "name": "Generator Current Limit",
        "description": "Maximum generator input current (from battery)",
        "icon": "mdi:current-ac",
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricCurrent.AMPERE,
        "category": "power",
    },
    "v.g.current": {
        "name": "Generator Current",
        "description": "Momentary generator input current (from battery)",
        "icon": "mdi:current-ac",
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricCurrent.AMPERE,
        "category": "power",
    },
    "v.g.duration.empty": {
        "name": "Time to Empty",
        "description": "Estimated time remaining for full discharge",
        "icon": "mdi:timer",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTime.MINUTES,
        "category": "power",
    },
    "v.g.duration.range": {
        "name": "Time to Range Limit",
        "description": "Estimated time for range limit",
        "icon": "mdi:timer",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTime.MINUTES,
        "category": "power",
    },
    "v.g.duration.soc": {
        "name": "Time to SOC Limit",
        "description": "Estimated time for SOC limit",
        "icon": "mdi:timer",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTime.MINUTES,
        "category": "power",
    },
    "v.g.efficiency": {
        "name": "Generator Efficiency",
        "description": "Momentary generator efficiency",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER_FACTOR,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": "power",
    },
    "v.g.kwh": {
        "name": "Generated Energy",
        "description": "Energy sum generated in the running session",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "category": "power",
    },
    "v.g.kwh.grid": {
        "name": "Grid Energy Sent",
        "description": "Energy sent to grid during running session",
        "icon": "mdi:transmission-tower",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "category": "power",
    },
    "v.g.kwh.grid.total": {
        "name": "Total Grid Energy Sent",
        "description": "Energy sent to grid total",
        "icon": "mdi:transmission-tower",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "category": "power",
    },
    "v.g.limit.range": {
        "name": "Generator Range Limit",
        "description": "Minimum range limit for generator mode",
        "icon": "mdi:map-marker-distance",
        "device_class": SensorDeviceClass.DISTANCE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfLength.KILOMETERS,
        "category": "power",
    },
    "v.g.limit.soc": {
        "name": "Generator SOC Limit",
        "description": "Minimum SOC limit for generator mode",
        "icon": "mdi:battery",
        "device_class": SensorDeviceClass.BATTERY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": "power",
    },
    "v.g.mode": {
        "name": "Generator Mode",
        "description": "Generator mode",
        "icon": "mdi:flash",
        "category": "power",
    },
    "v.g.pilot": {
        "name": "Generator Pilot Signal",
        "description": "Generator pilot signal present",
        "icon": "mdi:connection",
        "device_class": BinarySensorDeviceClass.CONNECTIVITY,
        "category": "power",
    },
    "v.g.power": {
        "name": "Generator Power",
        "description": "Momentary generator output power",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.KILO_WATT,
        "category": "power",
    },
    "v.g.state": {
        "name": "Generator State",
        "description": "Generator state",
        "icon": "mdi:flash",
        "category": "power",
    },
    "v.g.substate": {
        "name": "Generator Substate",
        "description": "Generator substate",
        "icon": "mdi:flash",
        "category": "power",
    },
    "v.g.temp": {
        "name": "Generator Temperature",
        "description": "Generator temperature",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "category": "power",
    },
    "v.g.time": {
        "name": "Generator Run Time",
        "description": "Duration of generator running",
        "icon": "mdi:timer",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTime.SECONDS,
        "category": "power",
    },
    "v.g.timermode": {
        "name": "Generator Timer Mode",
        "description": "Generator timer enabled state",
        "icon": "mdi:timer",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "category": "power",
    },
    "v.g.timerstart": {
        "name": "Generator Timer Start",
        "description": "Time generator is due to start",
        "icon": "mdi:timer",
        "device_class": SensorDeviceClass.TIMESTAMP,
        "category": "power",
    },
    "v.g.timestamp": {
        "name": "Last Generation End Time",
        "description": "Date & time of last generation end",
        "icon": "mdi:timer-off",
        "device_class": SensorDeviceClass.TIMESTAMP,
        "category": "power",
    },
    "v.g.type": {
        "name": "Generator Connection Type",
        "description": "Connection type (chademo, ccs, …)",
        "icon": "mdi:ev-plug-type2",
        "category": "power",
    },
    "v.g.voltage": {
        "name": "Generator Voltage",
        "description": "Momentary generator output voltage",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "category": "power",
    },
}
