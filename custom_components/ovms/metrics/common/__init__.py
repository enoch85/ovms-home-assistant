"""Common metrics for OVMS integration."""

from .battery import BATTERY_METRICS
from .charging import CHARGING_METRICS
from .climate import CLIMATE_METRICS
from .door import DOOR_METRICS
from .location import LOCATION_METRICS
from .motor import MOTOR_METRICS
from .system import SYSTEM_METRICS
from .trip import TRIP_METRICS
from .device import DEVICE_METRICS
from .diagnostic import DIAGNOSTIC_METRICS
from .power import POWER_METRICS
from .network import NETWORK_METRICS
from .tire import TIRE_METRICS

# Export all metrics as a single dictionary for convenience
__all__ = [
    "BATTERY_METRICS",
    "CHARGING_METRICS",
    "CLIMATE_METRICS",
    "DOOR_METRICS",
    "LOCATION_METRICS",
    "MOTOR_METRICS",
    "SYSTEM_METRICS",
    "TRIP_METRICS",
    "DEVICE_METRICS",
    "DIAGNOSTIC_METRICS",
    "POWER_METRICS",
    "NETWORK_METRICS",
    "TIRE_METRICS",
]
