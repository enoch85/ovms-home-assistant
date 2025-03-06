"""Support for tracking OVMS vehicles."""
import logging
import json
from typing import Any, Dict, Optional

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN, LOGGER_NAME
from .mqtt import SIGNAL_ADD_ENTITIES, SIGNAL_UPDATE_ENTITY
from .entity import OVMSBaseEntity
from .helpers.error_handler import OVMSError

_LOGGER = logging.getLogger(LOGGER_NAME)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up device tracker for OVMS component."""
    @callback
    def async_add_device_tracker(data: Dict[str, Any]) -> None:
        """Add device tracker based on discovery data."""
        if data["entity_type"] != "device_tracker":
            return
            
        _LOGGER.info("Adding device tracker for: %s", data["name"])
        
        tracker = OVMSDeviceTracker(
            data["unique_id"],
            data["name"],
            data["topic"],
            data["payload"],
            data["device_info"],
            data["attributes"],
            data.get("friendly_name"),
        )
        
        async_add_entities([tracker])
    
    # Subscribe to discovery events
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_ADD_ENTITIES, async_add_device_tracker)
    )


class OVMSDeviceTracker(OVMSBaseEntity, TrackerEntity):
    """OVMS device tracker."""
    
    def __init__(
        self,
        unique_id: str,
        name: str,
        topic: str,
        initial_payload: str,
        device_info: DeviceInfo,
        attributes: Dict[str, Any],
        friendly_name: Optional[str] = None,
    ) -> None:
        """Initialize the device tracker."""
        super().__init__(unique_id, name, topic, initial_payload, device_info, attributes, friendly_name)
        
        # Set specific TrackerEntity attributes
        self._attr_source_type = SourceType.GPS
        self._attr_icon = "mdi:car-electric"
    
    def _process_initial_state(self, initial_payload: str) -> None:
        """Process the initial state payload."""
        # Try to parse location
        self._parse_payload(initial_payload)
    
    async def _handle_restore_state(self, state) -> None:
        """Handle state restore."""
        # Restore attributes if available
        if state.attributes:
            # Only restore attributes that don't affect internal state management
            restorable_attrs = {
                k: v for k, v in state.attributes.items()
                if k not in ["source_type", "latitude", "longitude"]
            }
            self._attr_extra_state_attributes.update(restorable_attrs)
            
            # Restore location data
            if "latitude" in state.attributes and "longitude" in state.attributes:
                self._attr_latitude = state.attributes["latitude"]
                self._attr_longitude = state.attributes["longitude"]
                
                # Restore optional location attributes
                for attr in ["altitude", "heading", "speed"]:
                    if attr in state.attributes:
                        self._attr_extra_state_attributes[attr] = state.attributes[attr]
    
    def _handle_update(self, payload: str) -> None:
        """Handle state updates."""
        # Parse the location payload
        self._parse_payload(payload)
        
        # Call parent method to update timestamp and process JSON
        super()._handle_update(payload)
        
        # Update the state
        self.async_write_ha_state()
    
    def _parse_payload(self, payload: str) -> None:
        """Parse the location payload."""
        _LOGGER.debug("Parsing location payload: %s", payload)
        
        try:
            # Try to parse as JSON
            data = json.loads(payload)
            
            if isinstance(data, dict):
                # Look for lat/lon values using different possible field names
                lat = None
                lon = None
                
                # Check for various naming conventions for GPS coordinates
                for lat_name in ["lat", "latitude", "LAT", "Latitude"]:
                    if lat_name in data:
                        lat = float(data[lat_name])
                        break
                        
                for lon_name in ["lon", "lng", "longitude", "LON", "Longitude"]:
                    if lon_name in data:
                        lon = float(data[lon_name])
                        break
                
                if lat is not None and lon is not None:
                    self._attr_latitude = lat
                    self._attr_longitude = lon
                    _LOGGER.debug("Parsed location: %f, %f", lat, lon)
                else:
                    _LOGGER.warning("Could not find lat/lon in JSON data: %s", data)
                    return
                
                # Check for additional attributes
                for attr_field, attr_name in [
                    (["alt", "altitude", "ALT", "Altitude"], "altitude"),
                    (["spd", "speed", "SPD", "Speed"], "speed"),
                    (["hdg", "heading", "bearing", "direction"], "heading"),
                    (["acc", "accuracy", "hor_acc", "horizontal_accuracy"], "accuracy"),
                ]:
                    for field in attr_field:
                        if field in data:
                            try:
                                self._attr_extra_state_attributes[attr_name] = float(data[field])
                                break
                            except (ValueError, TypeError):
                                pass
            
        except (ValueError, TypeError, json.JSONDecodeError):
            # Not JSON, try comma-separated values
            parts = payload.split(",")
            if len(parts) >= 2:
                try:
                    lat = float(parts[0].strip())
                    lon = float(parts[1].strip())
                    
                    if -90 <= lat <= 90 and -180 <= lon <= 180:
                        self._attr_latitude = lat
                        self._attr_longitude = lon
                        _LOGGER.debug("Parsed location from CSV: %f, %f", lat, lon)
                        
                        # If we have more parts, they might be altitude, speed, etc.
                        if len(parts) >= 3:
                            try:
                                self._attr_extra_state_attributes["altitude"] = float(parts[2].strip())
                            except (ValueError, TypeError):
                                pass
                                
                        if len(parts) >= 4:
                            try:
                                self._attr_extra_state_attributes["speed"] = float(parts[3].strip())
                            except (ValueError, TypeError):
                                pass
                                
                        if len(parts) >= 5:
                            try:
                                self._attr_extra_state_attributes["heading"] = float(parts[4].strip())
                            except (ValueError, TypeError):
                                pass
                    else:
                        _LOGGER.warning("Invalid lat/lon values: %f, %f", lat, lon)
                except (ValueError, TypeError):
                    _LOGGER.warning("Could not parse location data as CSV: %s", payload)
