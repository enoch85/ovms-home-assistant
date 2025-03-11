"""Support for OVMS sensors."""
import logging
import json
from typing import Any, Dict, Optional, List

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util
from homeassistant.helpers.event import async_track_state_change
from homeassistant.components import device_tracker

from .const import (
    DOMAIN,
    LOGGER_NAME,
    SIGNAL_ADD_ENTITIES,
    SIGNAL_UPDATE_ENTITY
)

from .metrics import (
    METRIC_DEFINITIONS,
    TOPIC_PATTERNS,
    get_metric_by_path,
    get_metric_by_pattern,
)

_LOGGER = logging.getLogger(LOGGER_NAME)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up OVMS location sensors based on a config entry."""
    @callback
    def async_add_location_sensor(data: Dict[str, Any]) -> None:
        """Add location sensor based on discovery data."""
        try:
            if data["entity_type"] != "device_tracker":
                return

            _LOGGER.info("Adding location sensor: %s", data.get("friendly_name", data.get("name", "unknown")))

            # Create sensors instead of device_tracker entities
            sensor = OVMSLocationSensor(
                data.get("unique_id", ""),
                data.get("name", ""),
                data.get("topic", ""),
                data.get("payload", ""),
                data.get("device_info", {}),
                data.get("attributes", {}),
                hass,
                data.get("friendly_name"),
            )

            async_add_entities([sensor])
            
            # If this is a latitude or longitude sensor, set up the device tracker
            if ("latitude" in data.get("name", "").lower() or "longitude" in data.get("name", "").lower()):
                setup_device_tracker(hass, data.get("device_info", {}).get("identifiers", []))
                
        except Exception as ex:
            _LOGGER.exception("Error adding location sensor: %s", ex)

    # Subscribe to discovery events
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_ADD_ENTITIES, async_add_location_sensor)
    )

def setup_device_tracker(hass: HomeAssistant, identifiers: List) -> None:
    """Set up a device tracker that uses latitude and longitude sensors."""
    # Extract vehicle_id from identifiers
    vehicle_id = None
    for identifier in identifiers:
        if isinstance(identifier, tuple) and len(identifier) >= 2:
            # Identifier format is typically (DOMAIN, vehicle_id)
            vehicle_id = identifier[1]
            break
    
    if not vehicle_id:
        _LOGGER.warning("Could not extract vehicle_id from identifiers")
        return
        
    _LOGGER.info("Setting up device tracker for vehicle: %s", vehicle_id)
    
    # Define the sensors to track
    lat_sensor = f"sensor.ovms_{vehicle_id}_metric_v_p_latitude"
    lon_sensor = f"sensor.ovms_{vehicle_id}_metric_v_p_longitude"
    
    # Check if both sensors exist
    if (not hass.states.get(lat_sensor)) or (not hass.states.get(lon_sensor)):
        # Set up state change listener to wait for sensors to be created
        @callback
        def sensor_state_listener(entity_id, old_state, new_state):
            """React to sensor state changes."""
            # Check if both sensors exist now
            if (hass.states.get(lat_sensor)) and (hass.states.get(lon_sensor)):
                _LOGGER.info("Both lat/lon sensors available, creating device tracker for %s", vehicle_id)
                create_device_tracker(hass, vehicle_id)
                # Remove this listener
                if remove_listener:
                    remove_listener()
        
        # Track state changes for both sensors
        remove_listener = async_track_state_change(
            hass, [lat_sensor, lon_sensor], sensor_state_listener
        )
    else:
        # Sensors already exist, create tracker immediately
        create_device_tracker(hass, vehicle_id)

def create_device_tracker(hass: HomeAssistant, vehicle_id: str) -> None:
    """Create a device tracker for the vehicle using see service."""
    # Check if sensors exist
    lat_sensor = f"sensor.ovms_{vehicle_id}_metric_v_p_latitude"
    lon_sensor = f"sensor.ovms_{vehicle_id}_metric_v_p_longitude"
    
    if not (hass.states.get(lat_sensor) and hass.states.get(lon_sensor)):
        _LOGGER.warning("Cannot create device tracker, sensors not available")
        return
    
    @callback
    def location_state_changed(entity_id, old_state, new_state):
        """Update device tracker when location changes."""
        # Skip if no new state or either sensor is unavailable
        if not new_state or not hass.states.get(lat_sensor) or not hass.states.get(lon_sensor):
            return
            
        lat = hass.states.get(lat_sensor).state
        lon = hass.states.get(lon_sensor).state
        
        # Skip if either value is unknown or unavailable
        if lat in ('unknown', 'unavailable') or lon in ('unknown', 'unavailable'):
            return
            
        try:
            # Convert to float to validate
            lat_float = float(lat)
            lon_float = float(lon)
            
            # Only proceed if values are in valid range
            if -90 <= lat_float <= 90 and -180 <= lon_float <= 180:
                _LOGGER.debug("Updating device tracker for %s: %s, %s", vehicle_id, lat, lon)
                hass.services.call(
                    "device_tracker", 
                    "see", 
                    {
                        "dev_id": vehicle_id,
                        "gps": [lat, lon],
                        "source_type": "gps",
                    }
                )
        except (ValueError, TypeError):
            _LOGGER.debug("Invalid coordinates for device tracker: %s, %s", lat, lon)
    
    # Listen for state changes on both sensors
    async_track_state_change(
        hass, [lat_sensor, lon_sensor], location_state_changed
    )
    
    # Trigger initial update if both sensors have values
    lat_state = hass.states.get(lat_sensor)
    lon_state = hass.states.get(lon_sensor)
    
    if lat_state and lon_state and lat_state.state not in ('unknown', 'unavailable') and lon_state.state not in ('unknown', 'unavailable'):
        try:
            lat = float(lat_state.state)
            lon = float(lon_state.state)
            
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                _LOGGER.debug("Setting initial device tracker location for %s", vehicle_id)
                hass.services.call(
                    "device_tracker", 
                    "see", 
                    {
                        "dev_id": vehicle_id,
                        "gps": [lat, lon],
                        "source_type": "gps",
                    }
                )
        except (ValueError, TypeError):
            pass


class OVMSLocationSensor(SensorEntity, RestoreEntity):
    """Representation of an OVMS location sensor."""

    def __init__(
        self,
        unique_id: str,
        name: str,
        topic: str,
        initial_payload: Any,
        device_info: DeviceInfo,
        attributes: Dict[str, Any],
        hass: Optional[HomeAssistant] = None,
        friendly_name: Optional[str] = None,
    ) -> None:
        """Initialize the sensor."""
        self._attr_unique_id = unique_id
        self._internal_name = name
        self._attr_name = friendly_name or name.replace("_", " ").title()
        self._topic = topic
        self._attr_device_info = device_info
        self._attr_extra_state_attributes = {
            **attributes,
            "topic": topic,
            "last_updated": dt_util.utcnow().isoformat(),
        }
        self.hass = hass

        # Determine appropriate sensor properties based on name
        self._setup_sensor_properties()

        # Explicitly set entity_id - this ensures consistent naming
        if hass:
            self.entity_id = async_generate_entity_id(
                "sensor.{}",
                name.lower(),
                hass=hass,
            )

        # Set initial state if available
        if initial_payload:
            self._attr_native_value = self._parse_value(initial_payload)

    def _setup_sensor_properties(self) -> None:
        """Set up the sensor properties based on the sensor name."""
        # Default values
        self._attr_device_class = None
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = None
        self._attr_icon = "mdi:map-marker"
        
        # Check the name for specific types
        name_lower = self._internal_name.lower()
        
        if "latitude" in name_lower:
            self._attr_icon = "mdi:latitude"
            self._attr_extra_state_attributes["type"] = "latitude"
            
        elif "longitude" in name_lower:
            self._attr_icon = "mdi:longitude"
            self._attr_extra_state_attributes["type"] = "longitude"
            
        elif "gpsspeed" in name_lower:
            self._attr_device_class = SensorDeviceClass.SPEED
            self._attr_icon = "mdi:speedometer"
            
        elif "gpstime" in name_lower:
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
            self._attr_icon = "mdi:clock"
            
        elif "gpssq" in name_lower:
            self._attr_icon = "mdi:signal"
            self._attr_extra_state_attributes["type"] = "signal_quality"
            
        elif "gpshdop" in name_lower:
            self._attr_icon = "mdi:crosshairs-gps"
            self._attr_extra_state_attributes["type"] = "hdop"
            
        elif "gpslock" in name_lower:
            self._attr_icon = "mdi:crosshairs-gps"
            self._attr_extra_state_attributes["type"] = "gps_lock"
            
        elif "gpsmode" in name_lower:
            self._attr_icon = "mdi:crosshairs-gps"
            self._attr_extra_state_attributes["type"] = "gps_mode"
            
        elif "altitude" in name_lower:
            self._attr_device_class = SensorDeviceClass.DISTANCE
            self._attr_icon = "mdi:altimeter"
            
        elif "location" in name_lower and "latitude" not in name_lower and "longitude" not in name_lower:
            # For named locations
            self._attr_icon = "mdi:map-marker"
            self._attr_extra_state_attributes["type"] = "location_name"

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates."""
        await super().async_added_to_hass()

        # Restore previous state if available
        if (state := await self.async_get_last_state()) is not None:
            if state.state not in ["unavailable", "unknown", None]:
                # Only restore the state if it's not a special state
                self._attr_native_value = state.state
            # Restore attributes if available
            if state.attributes:
                # Don't overwrite entity attributes like unit, etc.
                saved_attributes = {
                    k: v for k, v in state.attributes.items()
                    if k not in ["device_class", "state_class", "unit_of_measurement"]
                }
                self._attr_extra_state_attributes.update(saved_attributes)

        @callback
        def update_state(payload: Any) -> None:
            """Update the sensor state."""
            self._attr_native_value = self._parse_value(payload)

            # Update timestamp attribute
            now = dt_util.utcnow()
            self._attr_extra_state_attributes["last_updated"] = now.isoformat()

            # Store raw payload for debugging if needed
            if payload and isinstance(payload, str) and len(payload) < 100:
                self._attr_extra_state_attributes["raw_payload"] = payload

            # Check if firmware version is included
            if isinstance(payload, dict) and "version" in payload:
                try:
                    device_info = self._attr_device_info or {}
                    device_info["sw_version"] = payload["version"]
                    self._attr_device_info = device_info
                except Exception as ex:
                    _LOGGER.debug("Failed to update firmware version: %s", ex)

            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_UPDATE_ENTITY}_{self.unique_id}",
                update_state,
            )
        )

    def _parse_value(self, value: Any) -> Any:
        """Parse the value from the payload."""
        if value is None:
            return None
            
        # If it's a dictionary, extract the relevant value
        if isinstance(value, dict):
            # Look for common field names based on sensor type
            sensor_type = self._attr_extra_state_attributes.get("type", "")
            
            if sensor_type == "latitude" or "latitude" in self._internal_name.lower():
                for key in ["lat", "latitude", "LAT", "Latitude"]:
                    if key in value:
                        return value[key]
                        
            elif sensor_type == "longitude" or "longitude" in self._internal_name.lower():
                for key in ["lon", "lng", "longitude", "LON", "Longitude"]:
                    if key in value:
                        return value[key]
                        
            # For other types, use the value as is
            return str(value)
            
        # String handling based on sensor type
        if isinstance(value, str):
            # Handle boolean-like values
            if value.lower() in ["true", "on", "yes", "1"]:
                return "on"
            if value.lower() in ["false", "off", "no", "0"]:
                return "off"
                
            # Return as is for string sensors
            return value
            
        # Return as is for other types
        return value
