"""Network metrics for OVMS integration."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import EntityCategory

# Network metrics
NETWORK_METRICS = {
    "m.net.mdm.iccid": {
        "name": "SIM ICCID",
        "description": "SIM ICCID",
        "icon": "mdi:sim",
        "category": "network",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "m.net.mdm.model": {
        "name": "Modem Model",
        "description": "Modem module hardware info",
        "icon": "mdi:cellphone",
        "category": "network",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "m.net.mdm.network": {
        "name": "GSM Network Provider",
        "description": "Current GSM network provider",
        "icon": "mdi:network",
        "category": "network",
    },
    "m.net.mdm.sq": {
        "name": "GSM Signal Quality",
        "description": "GSM signal quality",
        "icon": "mdi:signal",
        "device_class": SensorDeviceClass.SIGNAL_STRENGTH,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "dBm",
        "category": "network",
    },
    "m.net.provider": {
        "name": "Network Provider",
        "description": "Current primary network provider",
        "icon": "mdi:wifi",
        "category": "network",
    },
    "m.net.sq": {
        "name": "Network Signal Quality",
        "description": "Network signal quality",
        "icon": "mdi:signal",
        "device_class": SensorDeviceClass.SIGNAL_STRENGTH,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "dBm",
        "category": "network",
    },
    "m.net.type": {
        "name": "Network Type",
        "description": "Current network type (none/modem/wifi)",
        "icon": "mdi:network",
        "category": "network",
    },
    "m.net.wifi.network": {
        "name": "WiFi Network SSID",
        "description": "Current Wifi network SSID",
        "icon": "mdi:wifi",
        "category": "network",
    },
    "m.net.wifi.sq": {
        "name": "WiFi Signal Quality",
        "description": "WiFi signal quality",
        "icon": "mdi:wifi",
        "device_class": SensorDeviceClass.SIGNAL_STRENGTH,
        "state_class": SensorStateClass.MEASUREMENT,
        "unit": "dBm",
        "category": "network",
    },
    "m.net.mdm.mode": {
        "name": "Modem Mode",
        "description": "Current modem mode (e.g., WCDMA, Online)",
        "icon": "mdi:cellphone-wireless",
        "category": "network",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "m.net.mdm.netreg": {
        "name": "Modem Network Registration",
        "description": "Modem network registration status",
        "icon": "mdi:cellphone-check",
        "category": "network",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
}
