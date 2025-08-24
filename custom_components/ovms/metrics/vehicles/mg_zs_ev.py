"""MG ZS-EV specific metrics for OVMS integration."""

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
    UnitOfFrequency,
    EntityCategory,
)

# Custom unit constants
UNIT_AMPERE_HOUR = "Ah"

# MG ZS-EV specific metrics
MG_ZS_EV_METRICS = {
    # Battery system metrics
    "xmg.b.capacity": {
        "name": "MG ZS-EV Battery Capacity",
        "description": "Battery capacity in kWh",
        "icon": "mdi:battery",
        "device_class": SensorDeviceClass.ENERGY_STORAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "category": "mg_zs_ev",
    },
    "xmg.b.dod.lower": {
        "name": "MG ZS-EV Battery DOD Lower",
        "description": "Battery depth of discharge lower limit",
        "icon": "mdi:battery-low",
        "state_class": SensorStateClass.MEASUREMENT,
        "category": "mg_zs_ev",
    },
    "xmg.b.dod.upper": {
        "name": "MG ZS-EV Battery DOD Upper",
        "description": "Battery depth of discharge upper limit",
        "icon": "mdi:battery-high",
        "state_class": SensorStateClass.MEASUREMENT,
        "category": "mg_zs_ev",
    },
    "xmg.c.max.dc.charge": {
        "name": "MG ZS-EV Max DC Charge Power",
        "description": "Maximum DC charging power",
        "icon": "mdi:ev-station",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.KILO_WATT,
        "category": "mg_zs_ev",
    },
    "xmg.p.avg.consumption": {
        "name": "MG ZS-EV Average Consumption",
        "description": "Average energy consumption",
        "icon": "mdi:gauge",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfLength.MILES + "/" + UnitOfEnergy.KILO_WATT_HOUR,
        "category": "mg_zs_ev",
    },
    "xmg.p.trip.consumption": {
        "name": "MG ZS-EV Trip Consumption",
        "description": "Trip energy consumption",
        "icon": "mdi:gauge",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfLength.MILES + "/" + UnitOfEnergy.KILO_WATT_HOUR,
        "category": "mg_zs_ev",
    },

    # System status metrics
    "xmg.enable.polling": {
        "name": "MG ZS-EV Polling Enabled",
        "description": "Polling enabled status",
        "icon": "mdi:sync",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "category": "mg_zs_ev",
    },
    "xmg.state.gwm": {
        "name": "MG ZS-EV GWM State",
        "description": "Gateway module state",
        "icon": "mdi:chip",
        "category": "mg_zs_ev",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "xmg.state.poll": {
        "name": "MG ZS-EV Poll State",
        "description": "Polling state",
        "icon": "mdi:sync",
        "category": "mg_zs_ev",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "xmg.task.bcm": {
        "name": "MG ZS-EV BCM Task",
        "description": "Body control module task state",
        "icon": "mdi:chip",
        "category": "mg_zs_ev",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "xmg.task.gwm": {
        "name": "MG ZS-EV GWM Task",
        "description": "Gateway module task state",
        "icon": "mdi:chip",
        "category": "mg_zs_ev",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },

    # Battery technical metrics
    "xmg.v.bat.coolant.temp": {
        "name": "MG ZS-EV Battery Coolant Temperature",
        "description": "Battery coolant temperature",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "category": "mg_zs_ev",
    },
    "xmg.v.bat.error": {
        "name": "MG ZS-EV Battery Error",
        "description": "Battery error code",
        "icon": "mdi:battery-alert",
        "device_class": BinarySensorDeviceClass.PROBLEM,
        "category": "mg_zs_ev",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "xmg.v.bat.resistance": {
        "name": "MG ZS-EV Battery Resistance",
        "description": "Battery internal resistance",
        "icon": "mdi:resistor",
        "state_class": SensorStateClass.MEASUREMENT,
        "category": "mg_zs_ev",
    },
    "xmg.v.bat.voltage.bms": {
        "name": "MG ZS-EV BMS Battery Voltage",
        "description": "Battery voltage reported by BMS",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "suggested_display_precision": 2,
        "category": "mg_zs_ev",
    },
    "xmg.v.bat.voltage.vcu": {
        "name": "MG ZS-EV VCU Battery Voltage",
        "description": "Battery voltage reported by VCU",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "suggested_display_precision": 2,
        "category": "mg_zs_ev",
    },

    # BMS cell data metrics
    "xmg.v.bms.cell.voltage.max": {
        "name": "MG ZS-EV Max Cell Voltage",
        "description": "Maximum cell voltage",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "suggested_display_precision": 3,
        "category": "mg_zs_ev",
    },
    "xmg.v.bms.cell.voltage.min": {
        "name": "MG ZS-EV Min Cell Voltage",
        "description": "Minimum cell voltage",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "suggested_display_precision": 3,
        "category": "mg_zs_ev",
    },
    "xmg.v.bms.mainrelay.b": {
        "name": "MG ZS-EV BMS Main Relay B",
        "description": "BMS main relay B status",
        "icon": "mdi:electric-switch",
        "device_class": BinarySensorDeviceClass.POWER,
        "category": "mg_zs_ev",
    },
    "xmg.v.bms.mainrelay.g": {
        "name": "MG ZS-EV BMS Main Relay G",
        "description": "BMS main relay G status",
        "icon": "mdi:electric-switch",
        "device_class": BinarySensorDeviceClass.POWER,
        "category": "mg_zs_ev",
    },
    "xmg.v.bms.mainrelay.p": {
        "name": "MG ZS-EV BMS Main Relay P",
        "description": "BMS main relay P status",
        "icon": "mdi:electric-switch",
        "device_class": BinarySensorDeviceClass.POWER,
        "category": "mg_zs_ev",
    },
    "xmg.v.bms.time": {
        "name": "MG ZS-EV BMS Time",
        "description": "BMS time",
        "icon": "mdi:clock",
        "device_class": SensorDeviceClass.TIMESTAMP,
        "category": "mg_zs_ev",
    },

    # DC-DC converter metrics
    "xmg.v.dcdc.load": {
        "name": "MG ZS-EV DC-DC Converter Load",
        "description": "DC-DC converter load percentage",
        "icon": "mdi:percent",
        "device_class": SensorDeviceClass.POWER_FACTOR,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": "mg_zs_ev",
    },

    # Environmental metrics
    "xmg.v.env.faceoutlet.temp": {
        "name": "MG ZS-EV Face Outlet Temperature",
        "description": "Face outlet temperature",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "category": "mg_zs_ev",
    },

    # Ignition and operational state
    "xmg.v.ignition.state": {
        "name": "MG ZS-EV Ignition State",
        "description": "Ignition state",
        "icon": "mdi:power",
        "category": "mg_zs_ev",
    },

    # Motor and coolant metrics
    "xmg.v.m.coolant.temp": {
        "name": "MG ZS-EV Motor Coolant Temperature",
        "description": "Motor coolant temperature",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "category": "mg_zs_ev",
    },
    "xmg.v.m.torque": {
        "name": "MG ZS-EV Motor Torque",
        "description": "Motor torque",
        "icon": "mdi:gauge",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "Nm",
        "category": "mg_zs_ev",
    },

    # Radiator and cooling system
    "xmg.v.radiator.fan": {
        "name": "MG ZS-EV Radiator Fan",
        "description": "Radiator fan status",
        "icon": "mdi:fan",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "category": "mg_zs_ev",
    },

    # SOC and VCU metrics
    "xmg.v.soc.raw": {
        "name": "MG ZS-EV Raw SOC",
        "description": "Raw state of charge percentage",
        "icon": "mdi:battery",
        "device_class": SensorDeviceClass.BATTERY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": "mg_zs_ev",
    },
    "xmg.v.vcu.dcdc.input.current": {
        "name": "MG ZS-EV DCDC Input Current",
        "description": "DCDC converter input current",
        "icon": "mdi:current-ac",
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricCurrent.AMPERE,
        "category": "mg_zs_ev",
    },
    "xmg.v.vcu.dcdc.input.voltage": {
        "name": "MG ZS-EV DCDC Input Voltage",
        "description": "DCDC converter input voltage",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "suggested_display_precision": 2,
        "category": "mg_zs_ev",
    },
    "xmg.v.vcu.dcdc.mode": {
        "name": "MG ZS-EV DCDC Mode",
        "description": "DCDC converter mode",
        "icon": "mdi:car-electric",
        "category": "mg_zs_ev",
    },
    "xmg.v.vcu.dcdc.output.current": {
        "name": "MG ZS-EV DCDC Output Current",
        "description": "DCDC converter output current",
        "icon": "mdi:current-ac",
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricCurrent.AMPERE,
        "category": "mg_zs_ev",
    },
    "xmg.v.vcu.dcdc.output.voltage": {
        "name": "MG ZS-EV DCDC Output Voltage",
        "description": "DCDC converter output voltage",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "suggested_display_precision": 2,
        "category": "mg_zs_ev",
    },
    "xmg.v.vcu.dcdc.temp": {
        "name": "MG ZS-EV DCDC Temperature",
        "description": "DCDC converter temperature",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "category": "mg_zs_ev",
    },

    # Auth
    "xmg.auth.bcm": {
        "name": "MG ZS-EV BCM Auth",
        "description": "BCM Authorization status",
        "icon": "mdi:security",
        "device_class": BinarySensorDeviceClass.CONNECTIVITY,
        "category": "mg_zs_ev",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
}
