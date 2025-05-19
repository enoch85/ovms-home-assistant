"""Device identification metrics for OVMS integration."""

from homeassistant.helpers.entity import EntityCategory

# Device metrics
DEVICE_METRICS = {
    "v.type": {
        "name": "Vehicle Type",
        "description": "Vehicle type code",
        "icon": "mdi:car",
        "category": "device",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "device_class": None,  # Explicitly not numeric
        "state_class": None,
    },
    "v.vin": {
        "name": "Vehicle Identification Number",
        "description": "Vehicle identification number",
        "icon": "mdi:identifier",
        "category": "device",
        "entity_category": EntityCategory.DIAGNOSTIC,
        "device_class": None,  # Explicitly not numeric
        "state_class": None,
    },
}
