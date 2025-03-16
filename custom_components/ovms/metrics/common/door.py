"""Door metrics for OVMS integration."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
)

# Door metrics
DOOR_METRICS = {
    "v.d.cp": {
        "name": "Charge Port",
        "description": "Charge port open state",
        "icon": "mdi:ev-station",
        "device_class": BinarySensorDeviceClass.DOOR,
        "category": "door",
    },
    "v.d.fl": {
        "name": "Front Left Door",
        "description": "Front left door open state",
        "icon": "mdi:car-door",
        "device_class": BinarySensorDeviceClass.DOOR,
        "category": "door",
    },
    "v.d.fr": {
        "name": "Front Right Door",
        "description": "Front right door open state",
        "icon": "mdi:car-door",
        "device_class": BinarySensorDeviceClass.DOOR,
        "category": "door",
    },
    "v.d.hood": {
        "name": "Hood",
        "description": "Hood/frunk open state",
        "icon": "mdi:car-lifted-pickup",
        "device_class": BinarySensorDeviceClass.DOOR,
        "category": "door",
    },
    "v.d.rl": {
        "name": "Rear Left Door",
        "description": "Rear left door open state",
        "icon": "mdi:car-door",
        "device_class": BinarySensorDeviceClass.DOOR,
        "category": "door",
    },
    "v.d.rr": {
        "name": "Rear Right Door",
        "description": "Rear right door open state",
        "icon": "mdi:car-door",
        "device_class": BinarySensorDeviceClass.DOOR,
        "category": "door",
    },
    "v.d.trunk": {
        "name": "Trunk",
        "description": "Trunk open state",
        "icon": "mdi:car-back",
        "device_class": BinarySensorDeviceClass.DOOR,
        "category": "door",
    },
    "v.e.locked": {
        "name": "Vehicle Locked",
        "description": "Vehicle locked state",
        "icon": "mdi:lock",
        "device_class": BinarySensorDeviceClass.LOCK,
        "category": "door",
        "invert_state": True,  # Added to fix inverted reporting from OVMS
    },
}
