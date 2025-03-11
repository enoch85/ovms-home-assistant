"""Device tracker for OVMS Integration."""
import logging
import json
from typing import Any, Dict, Optional, Tuple

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    DOMAIN,
    LOGGER_NAME,
    SIGNAL_UPDATE_ENTITY,
)

_LOGGER = logging.getLogger(LOGGER_NAME)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up device tracker for OVMS component."""
    _LOGGER.debug("Setting up OVMS device trackers")

    @callback
    def async_add_device_tracker(entity_data):
        """Add OVMS device tracker."""
        try:
            if entity_data["entity_type"] != "device_tracker":
                return

            _LOGGER.debug("Adding OVMS device tracker: %s", entity_data["friendly_name"])
            device_tracker = OVMSDeviceTracker(
                entity_data["unique_id"],
                entity_data["name"],
                entity_data["friendly_name"],
                entity_data["device_info"],
                entity_data["attributes"],
            )
            async_add_entities([device_tracker])
        except Exception as ex:
            _LOGGER.exception("Error adding device tracker: %s", ex)

    # Subscribe to new entities being added
    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            "ovms_add_entities",
            async_add_device_tracker,
        )
    )


class OVMSDeviceTracker(TrackerEntity):
    """Represent an OVMS Device Tracker."""

    def __init__(
        self,
        unique_id: str,
        name: str,
        friendly_name: str,
        device_info: Dict[str, Any],
        attributes: Dict[str, Any],
    ) -> None:
        """Initialize the device tracker."""
        self._unique_id = unique_id
        self._name = name
        self._friendly_name = friendly_name
        self._device_info = device_info
        self._attributes = attributes or {}
        self._latitude = None
        self._longitude = None
        self._connected = False
        
        # Safe store for additional attributes
        self._extra_state_attributes = {}
        for key, value in self._attributes.items():
            self._extra_state_attributes[key] = value

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        try:
            _LOGGER.debug("Device tracker %s added to hass", self._name)
            
            # Register update callback
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass,
                    f"{SIGNAL_UPDATE_ENTITY}_{self._unique_id}",
                    self.update_state,
                )
            )
        except Exception as ex:
            _LOGGER.exception("Error in async_added_to_hass: %s", ex)

    @callback
    def update_state(self, payload) -> None:
        """Update the entity state based on payload data."""
        try:
            _LOGGER.debug("Device tracker update received")
            
            # Handle both string and dictionary payloads
            if isinstance(payload, str):
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    _LOGGER.error("Invalid JSON payload: %s", payload)
                    return
            else:
                data = payload
                
            # Process location data
            if isinstance(data, dict):
                if "latitude" in data and "longitude" in data:
                    try:
                        self._latitude = float(data["latitude"])
                        self._longitude = float(data["longitude"])
                        self._connected = True
                        _LOGGER.debug("Location updated successfully")
                    except (ValueError, TypeError) as err:
                        _LOGGER.error("Invalid coordinates: %s", err)
                        return
                        
                # Update any extra attributes
                for key, value in data.items():
                    if key not in ["latitude", "longitude"]:
                        self._extra_state_attributes[key] = value
            
            # Write state to HA
            self.async_write_ha_state()
        except Exception as ex:
            _LOGGER.exception("Error updating device tracker state: %s", ex)

    @property
    def unique_id(self) -> str:
        """Return a unique identifier for this device tracker."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Return the name of the device tracker."""
        return self._friendly_name
        
    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device information."""
        return self._device_info

    @property
    def source_type(self) -> str:
        """Return the source type of the device tracker."""
        return SourceType.GPS

    @property
    def latitude(self) -> Optional[float]:
        """Return latitude value of the device."""
        return self._latitude

    @property
    def longitude(self) -> Optional[float]:
        """Return longitude value of the device."""
        return self._longitude

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:car-electric"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return entity specific state attributes."""
        return self._extra_state_attributes
        
    @property
    def force_update(self) -> bool:
        """Disable forced updates."""
        return False

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False
