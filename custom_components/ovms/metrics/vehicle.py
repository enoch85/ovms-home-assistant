"""Vehicle identification metrics for OVMS integration."""
from homeassistant.helpers.entity import EntityCategory

# Category
CATEGORY_DEVICE = "device"

# Vehicle identification metrics
VEHICLE_METRICS = {
    "v.type": {
        "name": "Vehicle Type",
        "description": "Vehicle type code",
        "icon": "mdi:car",
        "category": CATEGORY_DEVICE,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "v.vin": {
        "name": "Vehicle Identification Number",
        "description": "Vehicle identification number",
        "icon": "mdi:identifier",
        "category": CATEGORY_DEVICE,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
}
