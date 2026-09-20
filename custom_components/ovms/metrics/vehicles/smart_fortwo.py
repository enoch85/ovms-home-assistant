"""Smart ForTwo specific metrics for OVMS integration."""

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
    UnitOfEnergyDistance,
    UnitOfLength,
    UnitOfPower,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfFrequency,
    EntityCategory,
)

from ...const import TRIP_DISTANCE_DISPLAY_PRECISION, UNIT_AMPERE_HOUR

# Vehicle metadata
VEHICLE_TYPE = "smart_fortwo"
VEHICLE_NAME = "Smart ForTwo"
# OVMS publishes Smart ForTwo (453/EQ) metrics under the "xsq" prefix - every
# metric key below uses it, and const.VEHICLE_TOPIC_PREFIXES maps "xsq" to this
# car. The prefix must match so config-flow discovery can auto-detect the
# vehicle; "xse" is the older Smart ED module and never matches these topics.
METRIC_PREFIX = "xsq."

# Metric names, types and units are taken from the firmware source
# (vehicle/OVMS.V3/components/vehicle_smarteq, the MyMetrics.Init*
# registrations) rather than its docs/index.rst, which lags the code. Server V3
# publishes every metric in its registered native unit, so "unit" below must
# match the registration exactly. Fixed-position vectors declare
# "vector_attributes"/"vector_state" so the sensor exposes one meaningful
# element as the state and the rest as named attributes instead of averaging
# unrelated values. Synced against upstream master 0712b636 (2026-09-20).
SMART_FORTWO_METRICS = {
    # ------------------------------------------------------------------
    # Current firmware: release 3.3.006 and every later EAP/edge build
    # ------------------------------------------------------------------
    "xsq.12v.trickle.count": {
        "name": "Smart ForTwo 12V Trickle Charge Cycles 24h",
        "description": (
            "Number of 12V battery trickle-charge cycles in the last 24 hours "
            "(Smart 453). Frequent trickle charging can indicate a weak 12V "
            "battery. Requires OVMS firmware 3.3.006+."
        ),
        "icon": "mdi:battery-clock",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "cycles",
        "category": "smart_fortwo",
    },
    "xsq.12v.undervolt.history": {
        "name": "Smart ForTwo 12V Undervoltage History",
        "description": "Ring buffer of recorded 12V undervoltage readings (below 12 V)",
        "icon": "mdi:car-battery",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "category": "smart_fortwo",
    },
    "xsq.adc.factor": {
        "name": "Smart ForTwo ADC Factor",
        "description": "Current ADC calibration factor used for the 12V reading",
        "icon": "mdi:tune",
        "state_class": SensorStateClass.MEASUREMENT,
        "suggested_display_precision": 3,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "category": "smart_fortwo",
    },
    "xsq.adc.factor.history": {
        "name": "Smart ForTwo ADC Factor History",
        "description": "Ring buffer of the last calculated ADC calibration factors",
        "icon": "mdi:tune",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "category": "smart_fortwo",
    },
    "xsq.bcm.state": {
        "name": "Smart ForTwo BCM State",
        "description": "Vehicle state reported by the body control module",
        "icon": "mdi:car-info",
        "category": "smart_fortwo",
    },
    "xsq.bms.cap": {
        "name": "Smart ForTwo Battery Capacity",
        "description": (
            "BMS capacity vector [usable_max, init, estimate, loss_pct, usable]; "
            "capacities in Ah, loss in percent. The state is the currently "
            "usable capacity."
        ),
        "icon": "mdi:battery-heart-variant",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UNIT_AMPERE_HOUR,
        "suggested_display_precision": 2,
        "category": "smart_fortwo",
        "vector_attributes": ["usable_max", "init", "estimate", "loss_pct", "usable"],
        "vector_state": "usable",
    },
    "xsq.bms.cell.resistance": {
        "name": "Smart ForTwo Cell Resistance",
        "description": "Relative internal resistance factor of each of the 96 cells",
        "icon": "mdi:resistor",
        "state_class": SensorStateClass.MEASUREMENT,
        "suggested_display_precision": 4,
        "category": "smart_fortwo",
        "has_cell_data": True,
    },
    "xsq.bms.contact": {
        "name": "Smart ForTwo HV Contactor State",
        "description": "High voltage contactor state text",
        "icon": "mdi:electric-switch",
        "category": "smart_fortwo",
    },
    "xsq.bms.contactor.cycles": {
        "name": "Smart ForTwo HV Contactor Cycles Remaining",
        "description": (
            "Remaining HV battery contactor switching cycles on Smart 453. "
            "The BMS counts down from 200000; reaching 0 leaves the car "
            "undriveable, and a sudden large drop can signal the contactor "
            "counter glitch. OVMS publishes xsq.bms.contactor.cycles as a "
            "vector [max, now, consumed, diff, cycles_last_hour]; 'now' is the "
            "remaining count and the others are exposed as attributes. "
            "Requires OVMS firmware 3.3.006+ (see 'xsq hvcycles')."
        ),
        "icon": "mdi:counter",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "cycles",
        "category": "smart_fortwo",
        # Heterogeneous vector: handled by the sensor's config-driven vector
        # path so the state is the remaining count, not the mean of all five.
        "vector_attributes": ["max", "now", "consumed", "diff", "cycles_last_hour"],
        "vector_state": "now",
    },
    "xsq.bms.energy.nominal": {
        "name": "Smart ForTwo Battery Nominal Energy",
        "description": "Nominal energy content of the HV battery",
        "icon": "mdi:battery",
        "device_class": SensorDeviceClass.ENERGY_STORAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "category": "smart_fortwo",
    },
    "xsq.bms.ev.mode": {
        "name": "Smart ForTwo EV Mode",
        "description": "EV operation mode",
        "icon": "mdi:car-electric",
        "category": "smart_fortwo",
    },
    "xsq.bms.fusi": {
        "name": "Smart ForTwo BMS FUSI Mode",
        "description": "BMS functional safety (FUSI) mode text",
        "icon": "mdi:shield-check",
        "category": "smart_fortwo",
    },
    "xsq.bms.id.basic.parts": {
        "name": "Smart ForTwo BMS Basic Parts",
        "description": "BMS basic part list (part number / hardware / approval, hex)",
        "icon": "mdi:identifier",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "category": "smart_fortwo",
    },
    "xsq.bms.id.hw.version": {
        "name": "Smart ForTwo BMS Hardware Version",
        "description": "BMS hardware version",
        "icon": "mdi:identifier",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "category": "smart_fortwo",
    },
    "xsq.bms.id.ident.data": {
        "name": "Smart ForTwo BMS Identification",
        "description": (
            "BMS identification record: part number, supplier, diagnostic "
            "version, hardware, software, basic part, edition and calibration"
        ),
        "icon": "mdi:identifier",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "category": "smart_fortwo",
    },
    "xsq.bms.id.mfr": {
        "name": "Smart ForTwo BMS Manufacturer Code",
        "description": "BMS manufacturer identification code",
        "icon": "mdi:identifier",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "category": "smart_fortwo",
    },
    "xsq.bms.id.part.no": {
        "name": "Smart ForTwo BMS Part Number",
        "description": "BMS part number",
        "icon": "mdi:identifier",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "category": "smart_fortwo",
    },
    "xsq.bms.id.sw.version": {
        "name": "Smart ForTwo BMS Software Version",
        "description": "BMS software version (hex)",
        "icon": "mdi:identifier",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "category": "smart_fortwo",
    },
    # The two interlock flags are firmware booleans (1 = interlock loop closed)
    # and have always been binary sensors: before they had a definition the
    # generic "lock" pattern matched "interlock". They must stay binary sensors,
    # because the platform is part of an entity's registry identity - turning
    # them into sensors would orphan the existing entities. PLUG reads
    # "plugged in" for a closed loop, where LOCK read "unlocked".
    "xsq.bms.interlock.hvplug": {
        "name": "Smart ForTwo HV Plug Interlock",
        "description": "HV plug interlock loop closed, as reported by the BMS",
        "icon": "mdi:power-plug-battery",
        "device_class": BinarySensorDeviceClass.PLUG,
        "category": "smart_fortwo",
    },
    "xsq.bms.interlock.service": {
        "name": "Smart ForTwo Service Interlock",
        "description": (
            "Service disconnect interlock loop closed, as reported by the BMS"
        ),
        "icon": "mdi:wrench-cog",
        "device_class": BinarySensorDeviceClass.PLUG,
        "category": "smart_fortwo",
    },
    "xsq.bms.mileage": {
        "name": "Smart ForTwo Battery Mileage",
        "description": "Distance driven with this HV battery",
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.DISTANCE,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfLength.KILOMETERS,
        "category": "smart_fortwo",
    },
    "xsq.bms.prod.data": {
        "name": "Smart ForTwo Battery Production Data",
        "description": "HV battery production data (serial, month/year)",
        "icon": "mdi:factory",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "category": "smart_fortwo",
    },
    "xsq.bms.safety": {
        "name": "Smart ForTwo BMS Safety Mode",
        "description": "BMS safety mode text",
        "icon": "mdi:shield-alert",
        "category": "smart_fortwo",
    },
    "xsq.bms.soc.recal.state": {
        "name": "Smart ForTwo SOC Recalibration State",
        "description": "State of the BMS state-of-charge recalibration",
        "icon": "mdi:battery-sync",
        "category": "smart_fortwo",
    },
    "xsq.bms.soc.values": {
        "name": "Smart ForTwo Real SOC",
        "description": (
            "BMS state-of-charge vector [kernel, real, min, max, display] in "
            "percent. The state is the real SOC; the displayed SOC is what "
            "the instrument cluster shows."
        ),
        "icon": "mdi:battery",
        "device_class": SensorDeviceClass.BATTERY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": "smart_fortwo",
        "vector_attributes": ["kernel", "real", "min", "max", "display"],
        "vector_state": "real",
    },
    "xsq.bms.soh": {
        "name": "Smart ForTwo Battery SOH",
        "description": "HV battery state of health as reported by the BMS",
        "icon": "mdi:battery-heart",
        "device_class": SensorDeviceClass.BATTERY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": "smart_fortwo",
    },
    "xsq.bms.voltage.state": {
        "name": "Smart ForTwo BMS Voltage State",
        "description": "BMS voltage state text",
        "icon": "mdi:flash-alert",
        "category": "smart_fortwo",
    },
    "xsq.bms.voltages": {
        "name": "Smart ForTwo Pack Voltage",
        "description": (
            "BMS voltage vector [cell_min, cell_max, cell_mean, cell_sum, pack, "
            "link, bms_12v, ocv_12v] in volts. The state is the pack voltage."
        ),
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "suggested_display_precision": 2,
        "category": "smart_fortwo",
        "vector_attributes": [
            "cell_min",
            "cell_max",
            "cell_mean",
            "cell_sum",
            "pack",
            "link",
            "bms_12v",
            "ocv_12v",
        ],
        "vector_state": "pack",
    },
    "xsq.ddt4all.canbyte": {
        "name": "Smart ForTwo DDT4all CAN Response",
        "description": "Raw CAN response bytes of the last DDT4all command (hex)",
        "icon": "mdi:hexadecimal",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "category": "smart_fortwo",
    },
    "xsq.driver.door.locked": {
        "name": "Smart ForTwo Driver Door Locked",
        "description": "Driver door lock state",
        "icon": "mdi:car-door-lock",
        "device_class": BinarySensorDeviceClass.LOCK,
        "category": "smart_fortwo",
        # Home Assistant's LOCK class is "on = unlocked" while OVMS reports
        # "yes = locked"; same inversion as the generic v.e.locked metric.
        "invert_state": True,
    },
    "xsq.ed4.values": {
        "name": "Smart ForTwo ED4scan Cell Count",
        "description": "Number of cells shown by the ED4scan style battery view",
        "icon": "mdi:numeric",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "category": "smart_fortwo",
    },
    "xsq.evc.12v.dcdc": {
        "name": "Smart ForTwo 12V DCDC Voltage",
        "description": (
            "EVC 12V system vector [volt_req (V), volt (V), power (W), "
            "usm_volt (V), batt_volt (V), batt_volt_req (V), amps (A), "
            "load (%)]. The state is the DC-DC converter output voltage."
        ),
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "suggested_display_precision": 2,
        "category": "smart_fortwo",
        "vector_attributes": [
            "volt_req",
            "volt",
            "power",
            "usm_volt",
            "batt_volt",
            "batt_volt_req",
            "amps",
            "load",
        ],
        "vector_state": "volt",
    },
    "xsq.evc.plug.detected": {
        # A firmware boolean, but deliberately NOT given a binary device class:
        # it has been a yes/no sensor since release 3.3.006, and moving it to
        # the binary_sensor platform would orphan that entity.
        "name": "Smart ForTwo Charge Plug Detected",
        "description": "Charging plug detected by the charger (yes / no)",
        "icon": "mdi:power-plug",
        "category": "smart_fortwo",
    },
    "xsq.evc.traceability": {
        "name": "Smart ForTwo EVC Traceability",
        "description": "EVC frame traceability information (ITG / factory / serial)",
        "icon": "mdi:identifier",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "category": "smart_fortwo",
    },
    "xsq.obd.charge.duration": {
        "name": "Smart ForTwo Charge Duration",
        "description": "Charge duration reported by the vehicle",
        "icon": "mdi:timer",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTime.MINUTES,
        "category": "smart_fortwo",
    },
    "xsq.obd.mt.day.prewarn": {
        "name": "Smart ForTwo Maintenance Prewarn Days",
        "description": "Days before the maintenance pre-warning is shown",
        "icon": "mdi:wrench-clock",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTime.DAYS,
        "category": "smart_fortwo",
    },
    "xsq.obd.mt.day.usual": {
        "name": "Smart ForTwo Maintenance Days",
        "description": "Days until the next scheduled maintenance",
        "icon": "mdi:wrench-clock",
        "device_class": SensorDeviceClass.DURATION,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTime.DAYS,
        "category": "smart_fortwo",
    },
    "xsq.obd.mt.km.usual": {
        "name": "Smart ForTwo Maintenance Distance",
        "description": "Distance until the next scheduled maintenance",
        "icon": "mdi:wrench",
        "device_class": SensorDeviceClass.DISTANCE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfLength.KILOMETERS,
        "category": "smart_fortwo",
    },
    "xsq.obd.mt.level": {
        "name": "Smart ForTwo Maintenance Level",
        "description": "Maintenance service level required",
        "icon": "mdi:wrench",
        "category": "smart_fortwo",
    },
    "xsq.obl.amps": {
        "name": "Smart ForTwo Charger Amps",
        "description": (
            "On-board charger AC current per phase/rail [l1, l2, l3]. The "
            "state is l1; the total is available as the generic charge current."
        ),
        "icon": "mdi:current-ac",
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricCurrent.AMPERE,
        "category": "smart_fortwo",
        "vector_attributes": ["l1", "l2", "l3"],
        "vector_state": "l1",
    },
    "xsq.obl.fastchg": {
        "name": "Smart ForTwo Fast Charging",
        "description": "Fast charging active",
        "icon": "mdi:ev-station",
        "device_class": BinarySensorDeviceClass.BATTERY_CHARGING,
        "category": "smart_fortwo",
    },
    "xsq.obl.leakdiag": {
        "name": "Smart ForTwo Charger Leakage Diagnostic",
        "description": "On-board charger leakage diagnostic status",
        "icon": "mdi:water-alert",
        "category": "smart_fortwo",
    },
    "xsq.obl.misc": {
        "name": "Smart ForTwo Charger Mains Frequency",
        "description": (
            "On-board charger vector [freq (Hz), ground_resistance (Ohm), "
            "max_current (A), dc_current (mA), hf10khz_current (mA), "
            "hf_current (mA), lf_current (mA)]. The state is the mains "
            "frequency."
        ),
        "icon": "mdi:sine-wave",
        "device_class": SensorDeviceClass.FREQUENCY,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfFrequency.HERTZ,
        "category": "smart_fortwo",
        "vector_attributes": [
            "freq",
            "ground_resistance",
            "max_current",
            "dc_current",
            "hf10khz_current",
            "hf_current",
            "lf_current",
        ],
        "vector_state": "freq",
    },
    "xsq.obl.power": {
        "name": "Smart ForTwo Charger Power",
        "description": (
            "On-board charger AC power per rail [l1, l2]. The state is l1; "
            "their sum is the generic charge power (v.c.power)."
        ),
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.KILO_WATT,
        "category": "smart_fortwo",
        "vector_attributes": ["l1", "l2"],
        "vector_state": "l1",
    },
    "xsq.obl.volts": {
        "name": "Smart ForTwo Charger Volts",
        "description": "On-board charger AC voltage per phase [l1, l2, l3]",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "suggested_display_precision": 2,
        "category": "smart_fortwo",
        "vector_attributes": ["l1", "l2", "l3"],
        "vector_state": "l1",
    },
    "xsq.odometer.start": {
        "name": "Smart ForTwo Odometer Start",
        "description": "Odometer at trip start",
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.DISTANCE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfLength.KILOMETERS,
        "category": "smart_fortwo",
    },
    "xsq.odometer.start.total": {
        "name": "Smart ForTwo Odometer Start Total",
        "description": "Odometer at the start of the total trip counter",
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.DISTANCE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfLength.KILOMETERS,
        "category": "smart_fortwo",
    },
    "xsq.odometer.trip": {
        "name": "Smart ForTwo Odometer Trip",
        "description": "Current trip distance",
        "icon": "mdi:map-marker-distance",
        "device_class": SensorDeviceClass.DISTANCE,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfLength.KILOMETERS,
        "suggested_display_precision": TRIP_DISTANCE_DISPLAY_PRECISION,
        "category": "smart_fortwo",
    },
    "xsq.odometer.trip.total": {
        "name": "Smart ForTwo Odometer Trip Total",
        "description": "Total trip distance",
        "icon": "mdi:counter",
        "device_class": SensorDeviceClass.DISTANCE,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfLength.KILOMETERS,
        "suggested_display_precision": TRIP_DISTANCE_DISPLAY_PRECISION,
        "category": "smart_fortwo",
    },
    "xsq.poll.state": {
        "name": "Smart ForTwo Poll State",
        "description": "CAN poller state (OFF / ON / RUNNING / CHARGING)",
        "icon": "mdi:state-machine",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "category": "smart_fortwo",
    },
    "xsq.tpms.dummy": {
        "name": "Smart ForTwo TPMS Test Pressure",
        "description": "Dummy pressure used for TPMS alert testing",
        "icon": "mdi:car-tire-alert",
        "device_class": SensorDeviceClass.PRESSURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPressure.KPA,
        "entity_category": EntityCategory.DIAGNOSTIC,
        "category": "smart_fortwo",
    },
    "xsq.tpms.lowbatt": {
        "name": "Smart ForTwo TPMS Sensor Low Battery",
        "description": (
            "TPMS sensor low-battery flags per wheel [fl, fr, rl, rr] "
            "(1 = low). The state is the front-left flag; all wheels are "
            "exposed as attributes."
        ),
        "icon": "mdi:battery-alert",
        "category": "smart_fortwo",
        "vector_attributes": ["fl", "fr", "rl", "rr"],
        "vector_state": "fl",
    },
    "xsq.tpms.missing": {
        "name": "Smart ForTwo TPMS Sensor Missing",
        "description": (
            "TPMS missing-transmission flags per wheel [fl, fr, rl, rr] "
            "(1 = missing). The state is the front-left flag; all wheels are "
            "exposed as attributes."
        ),
        "icon": "mdi:car-tire-alert",
        "category": "smart_fortwo",
        "vector_attributes": ["fl", "fr", "rl", "rr"],
        "vector_state": "fl",
    },
    "xsq.v.bat.consumption.best": {
        "name": "Smart ForTwo Best Consumption",
        "description": "Best average consumption",
        "icon": "mdi:leaf",
        "device_class": SensorDeviceClass.ENERGY_DISTANCE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfEnergyDistance.KILO_WATT_HOUR_PER_100_KM,
        "category": "smart_fortwo",
    },
    "xsq.v.bat.consumption.worst": {
        "name": "Smart ForTwo Worst Consumption",
        "description": "Worst average consumption",
        "icon": "mdi:speedometer",
        "device_class": SensorDeviceClass.ENERGY_DISTANCE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfEnergyDistance.KILO_WATT_HOUR_PER_100_KM,
        "category": "smart_fortwo",
    },
    "xsq.v.bat.serial": {
        "name": "Smart ForTwo Battery Serial",
        "description": "HV battery serial number",
        "icon": "mdi:identifier",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "category": "smart_fortwo",
    },
    "xsq.v.bus.awake": {
        # Published by release 3.3.006 only; upstream removed the metric on
        # 2026-05-25, so later EAP/edge builds no longer send it.
        "name": "Smart ForTwo Bus Awake",
        "description": "Vehicle bus awake status",
        "icon": "mdi:power",
        "device_class": BinarySensorDeviceClass.POWER,
        "category": "smart_fortwo",
    },
    "xsq.v.charge.bcb.power": {
        "name": "Smart ForTwo BCB Mains Power",
        "description": (
            "Power the battery charger block (BCB) draws from the mains, read "
            "passively from the CAN bus in 100 W steps. Unlike the generic "
            "charge power (v.c.power) it does not depend on CAN polling."
        ),
        "icon": "mdi:transmission-tower",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
        "category": "smart_fortwo",
    },
    "xsq.v.energy.aux": {
        "name": "Smart ForTwo Auxiliary Energy",
        "description": "Auxiliary consumption since mission start",
        "icon": "mdi:lightning-bolt",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "category": "smart_fortwo",
    },
    "xsq.v.energy.recd": {
        "name": "Smart ForTwo Energy Recovered",
        "description": "Energy recovered since mission start",
        "icon": "mdi:battery-plus",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "category": "smart_fortwo",
    },
    "xsq.v.energy.used": {
        "name": "Smart ForTwo Energy Used",
        "description": "Energy used since mission start",
        "icon": "mdi:battery-minus",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "category": "smart_fortwo",
    },
    "xsq.v.reset.consumption": {
        "name": "Smart ForTwo Trip Consumption",
        "description": "Average consumption since the trip counter reset",
        "icon": "mdi:chart-line",
        "device_class": SensorDeviceClass.ENERGY_DISTANCE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfEnergyDistance.KILO_WATT_HOUR_PER_100_KM,
        "category": "smart_fortwo",
    },
    "xsq.v.reset.distance": {
        "name": "Smart ForTwo Trip Distance",
        "description": "Distance since the trip counter reset",
        "icon": "mdi:map-marker-distance",
        "device_class": SensorDeviceClass.DISTANCE,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfLength.KILOMETERS,
        "suggested_display_precision": TRIP_DISTANCE_DISPLAY_PRECISION,
        "category": "smart_fortwo",
    },
    "xsq.v.reset.energy": {
        "name": "Smart ForTwo Trip Energy",
        "description": "Energy consumed since the trip counter reset",
        "icon": "mdi:lightning-bolt",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "category": "smart_fortwo",
    },
    "xsq.v.reset.speed": {
        "name": "Smart ForTwo Trip Average Speed",
        "description": "Average speed since the trip counter reset",
        "icon": "mdi:speedometer",
        "device_class": SensorDeviceClass.SPEED,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfSpeed.KILOMETERS_PER_HOUR,
        "category": "smart_fortwo",
    },
    "xsq.v.reset.time": {
        "name": "Smart ForTwo Trip Time",
        "description": "Driving time since the trip counter reset (hh:mm)",
        "icon": "mdi:clock",
        "category": "smart_fortwo",
    },
    "xsq.v.start.distance": {
        "name": "Smart ForTwo Distance Since Start",
        "description": "Distance driven since the vehicle was started",
        "icon": "mdi:map-marker-distance",
        "device_class": SensorDeviceClass.DISTANCE,
        "state_class": SensorStateClass.TOTAL_INCREASING,
        "unit": UnitOfLength.KILOMETERS,
        "suggested_display_precision": TRIP_DISTANCE_DISPLAY_PRECISION,
        "category": "smart_fortwo",
    },
    "xsq.v.start.time": {
        "name": "Smart ForTwo Time Since Start",
        "description": "Time since the vehicle was started (hh:mm)",
        "icon": "mdi:clock",
        "category": "smart_fortwo",
    },
    # ------------------------------------------------------------------
    # Legacy firmware: names only published by release 3.3.005 and earlier.
    # Upstream renamed or folded these into the vectors above; they are kept
    # so vehicles that have not updated their module keep proper entities.
    # ------------------------------------------------------------------
    "xsq.bms.amp2": {
        "name": "Smart ForTwo BMS Amp2",
        "description": "BMS secondary amp measurement",
        "icon": "mdi:current-ac",
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricCurrent.AMPERE,
        "category": "smart_fortwo",
    },
    "xsq.bms.amps": {
        "name": "Smart ForTwo BMS Amps",
        "description": "BMS current measurement",
        "icon": "mdi:current-ac",
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricCurrent.AMPERE,
        "category": "smart_fortwo",
    },
    "xsq.bms.batt.current": {
        "name": "Smart ForTwo Battery Current",
        "description": "Battery current",
        "icon": "mdi:current-ac",
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricCurrent.AMPERE,
        "category": "smart_fortwo",
    },
    "xsq.bms.batt.cv.sum": {
        "name": "Smart ForTwo Battery CV Sum",
        "description": "Sum of cell voltages",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "suggested_display_precision": 3,
        "category": "smart_fortwo",
    },
    "xsq.bms.batt.link.voltage": {
        "name": "Smart ForTwo Battery Link Voltage",
        "description": "Battery link voltage",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "suggested_display_precision": 2,
        "category": "smart_fortwo",
    },
    "xsq.bms.batt.power": {
        "name": "Smart ForTwo Battery Power",
        "description": "Battery power",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.KILO_WATT,
        "category": "smart_fortwo",
    },
    "xsq.bms.batt.voltage": {
        "name": "Smart ForTwo Battery Voltage",
        "description": "Battery voltage",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "suggested_display_precision": 2,
        "category": "smart_fortwo",
    },
    "xsq.bms.cv.range.max": {
        "name": "Smart ForTwo Cell Voltage Max",
        "description": "Maximum cell voltage",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "suggested_display_precision": 3,
        "category": "smart_fortwo",
    },
    "xsq.bms.cv.range.mean": {
        "name": "Smart ForTwo Cell Voltage Mean",
        "description": "Mean cell voltage",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "suggested_display_precision": 3,
        "category": "smart_fortwo",
    },
    "xsq.bms.cv.range.min": {
        "name": "Smart ForTwo Cell Voltage Min",
        "description": "Minimum cell voltage",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "suggested_display_precision": 3,
        "category": "smart_fortwo",
    },
    "xsq.bms.hv": {
        "name": "Smart ForTwo High Voltage",
        "description": "High voltage measurement",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "suggested_display_precision": 2,
        "category": "smart_fortwo",
    },
    "xsq.bms.hv.contact.state": {
        "name": "Smart ForTwo HV Contact State",
        "description": "High voltage contact state",
        "icon": "mdi:flash",
        "category": "smart_fortwo",
    },
    "xsq.bms.lv": {
        "name": "Smart ForTwo Low Voltage",
        "description": "Low voltage (12V) measurement",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "suggested_display_precision": 2,
        "category": "smart_fortwo",
    },
    "xsq.bms.power": {
        "name": "Smart ForTwo BMS Power",
        "description": "BMS power measurement",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.KILO_WATT,
        "category": "smart_fortwo",
    },
    "xsq.evc.ext.power": {
        "name": "Smart ForTwo External Power",
        "description": "External power connected",
        "icon": "mdi:power-plug",
        "device_class": BinarySensorDeviceClass.PLUG,
        "category": "smart_fortwo",
    },
    "xsq.evc.hv.energy": {
        "name": "Smart ForTwo HV Energy",
        "description": "High voltage energy measurement",
        "icon": "mdi:battery",
        "device_class": SensorDeviceClass.ENERGY_STORAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "category": "smart_fortwo",
    },
    "xsq.evc.lv.dcdc.amps": {
        "name": "Smart ForTwo DCDC Amps",
        "description": "DC-DC converter current",
        "icon": "mdi:current-ac",
        "device_class": SensorDeviceClass.CURRENT,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricCurrent.AMPERE,
        "category": "smart_fortwo",
    },
    "xsq.evc.lv.dcdc.load": {
        "name": "Smart ForTwo DCDC Load",
        "description": "DC-DC converter load percentage",
        "icon": "mdi:gauge",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": PERCENTAGE,
        "category": "smart_fortwo",
    },
    "xsq.evc.lv.dcdc.power": {
        "name": "Smart ForTwo DCDC Power",
        "description": "DC-DC converter power",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.POWER,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfPower.WATT,
        "category": "smart_fortwo",
    },
    "xsq.evc.lv.dcdc.state": {
        "name": "Smart ForTwo DCDC State",
        "description": "DC-DC converter state",
        "icon": "mdi:power",
        "category": "smart_fortwo",
    },
    "xsq.evc.lv.dcdc.volt": {
        "name": "Smart ForTwo DCDC Voltage",
        "description": "DC-DC converter voltage",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.VOLTAGE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfElectricPotential.VOLT,
        "suggested_display_precision": 2,
        "category": "smart_fortwo",
    },
    "xsq.evc.plug.present": {
        "name": "Smart ForTwo Plug Connected",
        "description": "Charge plug connection status",
        "icon": "mdi:power-plug",
        "device_class": BinarySensorDeviceClass.PLUG,
        "category": "smart_fortwo",
    },
    "xsq.obl.freq": {
        "name": "Smart ForTwo Charger Frequency",
        "description": "Charger frequency",
        "icon": "mdi:sine-wave",
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfFrequency.HERTZ,
        "category": "smart_fortwo",
    },
    "xsq.use.at.reset": {
        "name": "Smart ForTwo Energy At Reset",
        "description": "Energy usage at reset",
        "icon": "mdi:battery",
        "device_class": SensorDeviceClass.ENERGY,
        "state_class": SensorStateClass.TOTAL,
        "unit": UnitOfEnergy.KILO_WATT_HOUR,
        "category": "smart_fortwo",
    },
    "xsq.v.bms.temps": {
        "name": "Smart ForTwo BMS Temperatures",
        "description": "BMS temperature readings",
        "icon": "mdi:thermometer",
        "device_class": SensorDeviceClass.TEMPERATURE,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": UnitOfTemperature.CELSIUS,
        "category": "smart_fortwo",
    },
}
