"""Device identification metrics for OVMS integration."""

from homeassistant.const import EntityCategory

# Device metrics
DEVICE_METRICS = {
    "v.type": {
        "name": "Vehicle Type",
        "description": "Vehicle type code",
        "icon": "mdi:car",
        "category": "device",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "v.vin": {
        "name": "Vehicle Identification Number",
        "description": "Vehicle identification number",
        "icon": "mdi:identifier",
        "category": "device",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
}
