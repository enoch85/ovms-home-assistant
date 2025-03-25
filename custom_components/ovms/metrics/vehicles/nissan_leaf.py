"""Nissan Leaf specific metrics for OVMS integration."""

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
)
from homeassistant.helpers.entity import EntityCategory

# Custom unit constants
UNIT_AMPERE_HOUR = "Ah"

# Nissan Leaf specific metrics
NISSAN_LEAF_METRICS = {
    # BMS metrics
    "xnl.bms.balancing": {
        "name": "Nissan Leaf BMS Balancing",
        "description": "Battery cells currently being balanced",
        "icon": "mdi:battery-sync",
        "category": "nissan_leaf",
    },
    "xnl.bms.temp.int": {
        "name": "Nissan Leaf BMS Internal Temperature",
        "description": "BMS internal temperature sensors",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "category": "nissan_leaf",
        "has_cell_data": True,
    },
    "xnl.bms.thermistor": {
        "name": "Nissan Leaf BMS Thermistor",
        "description": "BMS thermistor readings",
        "icon": "mdi:thermometer",
        "state_class": SensorStateClass.MEASUREMENT,
        "category": "nissan_leaf",
        "has_cell_data": True,
    },

    # Climate control metrics
    "xnl.cc.fan.only": {
        "name": "Nissan Leaf Fan Only Mode",
        "description": "Climate control fan only mode",
        "icon": "mdi:fan",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "category": "nissan_leaf",
    },
    "xnl.cc.remotecool": {
        "name": "Nissan Leaf Remote Cooling",
        "description": "Remote cooling active state",
        "icon": "mdi:snowflake",
        "device_class": BinarySensorDeviceClass.COLD,
        "category": "nissan_leaf",
    },
    "xnl.cc.remoteheat": {
        "name": "Nissan Leaf Remote Heating",
        "description": "Remote heating active state",
        "icon": "mdi:fire",
        "device_class": BinarySensorDeviceClass.HEAT,
        "category": "nissan_leaf",
    },
    "xnl.cc.rqinprogress": {
        "name": "Nissan Leaf Climate Request In Progress",
        "description": "Climate control request in progress",
        "icon": "mdi:progress-clock",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "category": "nissan_leaf",
    },

    # Battery metrics
    "xnl.v.b.charge.limit": {
        "name": "Nissan Leaf Charge Limit",
        "description": "Maximum charging power",
        "icon": "mdi:battery-charging",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.KILO_WATT,
        "category": "nissan_leaf",
    },
    "xnl.v.b.e.available": {
        "name": "Nissan Leaf Available Energy",
        "description": "Available energy in battery",
        "icon": "mdi:battery",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "category": "nissan_leaf",
    },
    "xnl.v.b.e.capacity": {
        "name": "Nissan Leaf Energy Capacity",
        "description": "Total energy capacity of battery",
        "icon": "mdi:battery",
        "device_class": SensorDeviceClass.ENERGY_STORAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "category": "nissan_leaf",
    },
    "xnl.v.b.gids": {
        "name": "Nissan Leaf GIDs",
        "description": "Battery capacity measurement in GIDs",
        "icon": "mdi:battery-medium",
        "state_class": SensorStateClass.MEASUREMENT,
        "category": "nissan_leaf",
    },
    "xnl.v.b.heatergranted": {
        "name": "Nissan Leaf Heater Granted",
        "description": "Battery heater operation granted",
        "icon": "mdi:car-battery",
        "device_class": BinarySensorDeviceClass.HEAT,
        "category": "nissan_leaf",
    },
    "xnl.v.b.heaterpresent": {
        "name": "Nissan Leaf Heater Present",
        "description": "Battery heater present in vehicle",
        "icon": "mdi:heat-wave",
        "category": "nissan_leaf",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "xnl.v.b.heatrequested": {
        "name": "Nissan Leaf Heat Requested",
        "description": "Battery heating requested",
        "icon": "mdi:heat-wave",
        "device_class": BinarySensorDeviceClass.HEAT,
        "category": "nissan_leaf",
    },
    "xnl.v.b.hx": {
        "name": "Nissan Leaf Heat Exchange",
        "description": "Battery heat exchange value",
        "icon": "mdi:heat-wave",
        "state_class": SensorStateClass.MEASUREMENT,
        "category": "nissan_leaf",
    },
    "xnl.v.b.max.gids": {
        "name": "Nissan Leaf Maximum GIDs",
        "description": "Maximum GIDs for the battery when new",
        "icon": "mdi:battery-high",
        "state_class": SensorStateClass.MEASUREMENT,
        "category": "nissan_leaf",
    },
    "xnl.v.b.output.limit": {
        "name": "Nissan Leaf Power Output Limit",
        "description": "Maximum power output from battery",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.KILO_WATT,
        "category": "nissan_leaf",
    },
    "xnl.v.b.range.instrument": {
        "name": "Nissan Leaf Instrument Range",
        "description": "Range shown on the dashboard instrument",
        "icon": "mdi:map-marker-distance",
        "device_class": SensorDeviceClass.DISTANCE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfLength.KILOMETERS,
        "category": "nissan_leaf",
    },
    "xnl.v.b.regen.limit": {
        "name": "Nissan Leaf Regeneration Limit",
        "description": "Maximum regenerative braking power",
        "icon": "mdi:battery-charging",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.KILO_WATT,
        "category": "nissan_leaf",
    },
    "xnl.v.b.soc.instrument": {
        "name": "Nissan Leaf Instrument SOC",
        "description": "State of charge shown on dashboard",
        "icon": "mdi:battery",
        "device_class": SensorDeviceClass.BATTERY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": "nissan_leaf",
    },
    "xnl.v.b.soc.newcar": {
        "name": "Nissan Leaf New Car SOC",
        "description": "State of charge relative to new car capacity",
        "icon": "mdi:battery",
        "device_class": SensorDeviceClass.BATTERY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": "nissan_leaf",
    },
    "xnl.v.b.soc.nominal": {
        "name": "Nissan Leaf Nominal SOC",
        "description": "Nominal state of charge",
        "icon": "mdi:battery",
        "device_class": SensorDeviceClass.BATTERY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": "nissan_leaf",
    },
    "xnl.v.b.soh.instrument": {
        "name": "Nissan Leaf Instrument SOH",
        "description": "State of health shown on dashboard",
        "icon": "mdi:battery-heart",
        "device_class": SensorDeviceClass.BATTERY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": "nissan_leaf",
    },
    "xnl.v.b.soh.newcar": {
        "name": "Nissan Leaf New Car SOH",
        "description": "State of health compared to new car",
        "icon": "mdi:battery-heart",
        "device_class": SensorDeviceClass.BATTERY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": "nissan_leaf",
    },
    "xnl.v.b.type": {
        "name": "Nissan Leaf Battery Type",
        "description": "Battery type identifier",
        "icon": "mdi:car-battery",
        "category": "nissan_leaf",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },

    # Charging metrics
    "xnl.v.c.chargebars": {
        "name": "Nissan Leaf Charge Bars",
        "description": "Number of charge bars on display",
        "icon": "mdi:battery-charging",
        "state_class": SensorStateClass.MEASUREMENT,
        "category": "nissan_leaf",
    },
    "xnl.v.c.chargeminutes3kW": {
        "name": "Nissan Leaf Charge Time 3kW",
        "description": "Estimated minutes to full at 3kW",
        "icon": "mdi:timer",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "min",
        "category": "nissan_leaf",
    },
    "xnl.v.c.count.l0l1l2": {
        "name": "Nissan Leaf L0/L1/L2 Charge Count",
        "description": "Number of Level 0/1/2 charges",
        "icon": "mdi:counter",
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "category": "nissan_leaf",
    },
    "xnl.v.c.count.qc": {
        "name": "Nissan Leaf Quick Charge Count",
        "description": "Number of quick charges",
        "icon": "mdi:counter",
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "category": "nissan_leaf",
    },
    "xnl.v.c.duration": {
        "name": "Nissan Leaf Charge Duration",
        "description": "Various charge duration metrics",
        "icon": "mdi:timer",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "min",
        "category": "nissan_leaf",
    },
    "xnl.v.c.event.notification": {
        "name": "Nissan Leaf Charge Event Notification",
        "description": "Charging event notification",
        "icon": "mdi:bell",
        "category": "nissan_leaf",
    },
    "xnl.v.c.event.reason": {
        "name": "Nissan Leaf Charge Event Reason",
        "description": "Reason for charge event",
        "icon": "mdi:help-circle",
        "category": "nissan_leaf",
    },
    "xnl.v.c.limit.reason": {
        "name": "Nissan Leaf Charge Limit Reason",
        "description": "Reason for charge rate limitation",
        "icon": "mdi:speedometer-slow",
        "category": "nissan_leaf",
    },
    "xnl.v.c.quick": {
        "name": "Nissan Leaf Quick Charge Status",
        "description": "Quick charge status",
        "icon": "mdi:ev-station",
        "device_class": BinarySensorDeviceClass.BATTERY_CHARGING,
        "category": "nissan_leaf",
    },
    "xnl.v.c.state.previous": {
        "name": "Nissan Leaf Previous Charge State",
        "description": "Previous charging state",
        "icon": "mdi:battery-charging",
        "category": "nissan_leaf",
    },

    # Climate metrics
    "xnl.v.e.hvac.auto": {
        "name": "Nissan Leaf Auto HVAC",
        "description": "HVAC in automatic mode",
        "icon": "mdi:air-conditioner",
        "device_class": BinarySensorDeviceClass.RUNNING,
        "category": "nissan_leaf",
    },
}
