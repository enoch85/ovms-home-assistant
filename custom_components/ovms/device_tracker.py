"""Support for OVMS location tracking."""
import logging
import re
import time
from typing import Any, Dict, Optional, List

from homeassistant.components.device_tracker.const import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.core import HomeAssistant # Ensure HomeAssistant is imported
from typing import Optional # Ensure Optional is imported
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    LOGGER_NAME,
    SIGNAL_ADD_ENTITIES,
    SIGNAL_UPDATE_ENTITY
)
from .naming_service import EntityNamingService
from .attribute_manager import AttributeManager

_LOGGER = logging.getLogger(LOGGER_NAME)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up OVMS device tracker based on a config entry."""
    @callback
    def async_add_device_tracker(data: Dict[str, Any]) -> None:
        """Add device tracker based on discovery data."""
        try:
            if data["entity_type"] != "device_tracker":
                return

            _LOGGER.info("Adding device tracker: %s", data.get("friendly_name", data.get("name", "unknown")))

            # Create naming and attribute services
            config = dict(entry.data)  # Convert to dict to avoid MappingProxyType issues
            naming_service = EntityNamingService(config)
            attribute_manager = AttributeManager(config)

            tracker = OVMSDeviceTracker(
                data.get("unique_id", ""),
                data.get("name", ""),
                data.get("topic", ""),
                data.get("payload", {}),
                data.get("device_info", {}),
                data.get("attributes", {}),
                hass,
                data.get("friendly_name"),
                naming_service,
                attribute_manager
            )

            async_add_entities([tracker])
        except Exception as ex:
            _LOGGER.exception("Error adding device tracker: %s", ex)

    # Subscribe to discovery events
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_ADD_ENTITIES, async_add_device_tracker)
    )


class OVMSDeviceTracker(TrackerEntity, RestoreEntity):
    """OVMS Device Tracker Entity."""

    _attr_device_info: Optional[DeviceInfo] = None

    def __init__(
        self,
        unique_id: str,
        name: str,
        topic: str,
        initial_payload: Any,
        device_info: DeviceInfo, # Keep as DeviceInfo
        attributes: Dict[str, Any],
        hass: HomeAssistant, # Change to HomeAssistant (non-optional)
        friendly_name: Optional[str] = None,
        naming_service: Optional[EntityNamingService] = None,
        attribute_manager: Optional[AttributeManager] = None
    ) -> None:
        """Initialize the device tracker."""
        super().__init__() # Call super().__init__ for TrackerEntity
        self.hass = hass # Assign hass directly
        self._attr_unique_id = unique_id
        self._internal_name = name

        # Use services if provided, otherwise create internal defaults
        self.naming_service = naming_service or EntityNamingService({})
        self.attribute_manager = attribute_manager or AttributeManager({})

        # Extract vehicle ID
        vehicle_id = None

        # Try to extract from device info identifiers
        vehicle_id = self.naming_service.extract_vehicle_id_from_device_info(device_info)

        # If not found in device info, try extracting from name
        if not vehicle_id:
            vehicle_id = self.naming_service.extract_vehicle_id_from_name(name)

        # Set the device tracker friendly name per requirements
        if vehicle_id:
            self._attr_name = self.naming_service.create_device_tracker_name(vehicle_id)
        else:
            self._attr_name = friendly_name or name.replace("_", " ").title()

        self._topic = topic
        self._attr_device_info = device_info or {}

        # Process attributes
        self._attr_extra_state_attributes = attributes.copy() if attributes else {}

        # Add GPS attributes if needed
        if "gps_accuracy" not in self._attr_extra_state_attributes:
            gps_attributes = self.attribute_manager.get_gps_attributes(topic, initial_payload)
            self._attr_extra_state_attributes.update(gps_attributes)

        # Ensure topic and last_updated are present
        if topic:
            self._attr_extra_state_attributes["topic"] = topic
        if "last_updated" not in self._attr_extra_state_attributes:
            self._attr_extra_state_attributes["last_updated"] = dt_util.utcnow().isoformat()

        self._latitude = None
        self._longitude = None
        self._source_type = SourceType.GPS
        self._last_update_time = 0
        self._prev_latitude = None
        self._prev_longitude = None

        # Process initial payload
        if initial_payload:
            self._process_payload(initial_payload)

        # Explicitly set entity_id - this ensures consistent naming
        if hass:
            self.entity_id = async_generate_entity_id(
                "device_tracker.{}",
                name.lower(),
                hass=hass,
            )

    async def async_added_to_hass(self) -> None:
        """Handle when entity is added to hass."""
        await super().async_added_to_hass()
        if self.hass is None: # Add a check for self.hass
            _LOGGER.error("Hass object not available for %s", self.entity_id)
            return

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, 
                SIGNAL_UPDATE_ENTITY, 
                self._async_handle_update # This line was causing the error
            )
        )
        # Restore last known state
        if (state := await self.async_get_last_state()) is not None:
            # Restore attributes if available
            if state.attributes:
                # Keep specific attributes that are relevant
                for attr in ["latitude", "longitude", "source_type", "gps_accuracy"]:
                    if attr in state.attributes:
                        if attr == "latitude":
                            self._latitude = state.attributes[attr]
                            self._prev_latitude = state.attributes[attr]
                        elif attr == "longitude":
                            self._longitude = state.attributes[attr]
                            self._prev_longitude = state.attributes[attr]
                        else:
                            setattr(self, f"_{attr}", state.attributes[attr])

                # Don't overwrite entity attributes like unit, etc.
                saved_attributes = {
                    k: v for k, v in state.attributes.items()
                    if k not in ["latitude", "longitude", "source_type", "gps_accuracy"]
                }
                self._attr_extra_state_attributes.update(saved_attributes)

        @callback
        def update_state(payload: Any) -> None:
            """Update the tracker state."""
            self._process_payload(payload)

            # Update timestamp attribute
            self._attr_extra_state_attributes["last_updated"] = dt_util.utcnow().isoformat()

            # Process any JSON attributes if applicable
            if isinstance(payload, str):
                self._attr_extra_state_attributes = self.attribute_manager.process_json_payload(
                    payload, self._attr_extra_state_attributes
                )

            # Also update corresponding sensor entities
            try:
                # Signal sensor entities to update
                if self.latitude is not None:
                    async_dispatcher_send(
                        self.hass,
                        f"{SIGNAL_UPDATE_ENTITY}_{self.unique_id}_sensor",
                        self.latitude,
                    )

                if self.longitude is not None:
                    async_dispatcher_send(
                        self.hass,
                        f"{SIGNAL_UPDATE_ENTITY}_{self.unique_id}_sensor",
                        self.longitude,
                    )

                # If there are related entities we should update them too
                related_entities_sent = False
                if hasattr(self.hass.data.get(DOMAIN, {}), "entity_registry"):
                    # Try to get entity registry from domain data
                    for entry_id, data_item in self.hass.data[DOMAIN].items(): # renamed data to data_item
                        if hasattr(data_item, "entity_registry") and data_item.entity_registry:
                            entity_registry = data_item.entity_registry
                            if hasattr(entity_registry, "get_related_entities"):
                                related_entities = entity_registry.get_related_entities(self.unique_id)
                                for related_id in related_entities:
                                    # Create a location payload for sensors
                                    sensor_payload = {
                                        "value": self.latitude if "latitude" in related_id else self.longitude,
                                        "latitude": self.latitude,
                                        "longitude": self.longitude,
                                        "last_updated": dt_util.utcnow().isoformat()
                                    }

                                    async_dispatcher_send(
                                        self.hass,
                                        f"{SIGNAL_UPDATE_ENTITY}_{related_id}",
                                        sensor_payload,
                                    )
                                related_entities_sent = True
                                break

                # If we didn't update via entity registry, try a more direct approach
                if not related_entities_sent and self.latitude is not None and self.longitude is not None:
                    # Create a coordinates payload
                    location_payload = {
                        "latitude": self.latitude,
                        "longitude": self.longitude,
                        "last_updated": dt_util.utcnow().isoformat()
                    }

                    # Dispatch to latitude/longitude sensors based on their name pattern
                    lat_sensor_id = f"{self.unique_id}_latitude"
                    lon_sensor_id = f"{self.unique_id}_longitude"

                    async_dispatcher_send(
                        self.hass,
                        f"{SIGNAL_UPDATE_ENTITY}_{lat_sensor_id}",
                        location_payload,
                    )

                    async_dispatcher_send(
                        self.hass,
                        f"{SIGNAL_UPDATE_ENTITY}_{lon_sensor_id}",
                        location_payload,
                    )
            except Exception as ex:
                _LOGGER.exception("Error updating related entities: %s", ex)

            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_UPDATE_ENTITY}_{self.unique_id}",
                update_state,
            )
        )

    @callback
    async def _async_handle_update(self, data: Dict[str, Any]) -> None:
        """Handle an update dispatch."""
        if not self.hass: # Add a check for self.hass
            _LOGGER.error("Hass object not available in _async_handle_update for %s", self.entity_id)
            return
        
        # Find the update_state callback. 
        # This is a bit of a workaround as the callback is defined within async_added_to_hass
        # A more robust solution might involve passing the callback or storing it on the instance.
        # For now, we'll assume it's available via a closure or similar mechanism if this path is hit.
        # This part of the logic might need review if issues arise.
        
        # Call the existing update_state logic if it can be resolved
        # This assumes update_state is accessible here, which might not be true
        # depending on how it's defined and captured by async_dispatcher_connect.
        # If `update_state` is not in scope here, this will fail.
        # We need to ensure `update_state` is a method of the class or passed appropriately.

        # Let's redefine update_state as a method of the class for clarity and accessibility
        await self._update_state_method(data.get("payload"))

    @callback
    async def _update_state_method(self, payload: Any) -> None:
        """Update the tracker state. (Moved from async_added_to_hass)"""
        self._process_payload(payload)

        # Update timestamp attribute
        self._attr_extra_state_attributes["last_updated"] = dt_util.utcnow().isoformat()

        # Process any JSON attributes if applicable
        if isinstance(payload, str):
            self._attr_extra_state_attributes = self.attribute_manager.process_json_payload(
                payload, self._attr_extra_state_attributes
            )

        # Also update corresponding sensor entities
        try:
            # Signal sensor entities to update
            if self.latitude is not None:
                async_dispatcher_send(
                    self.hass,
                    f"{SIGNAL_UPDATE_ENTITY}_{self.unique_id}_sensor",
                    self.latitude,
                )

            if self.longitude is not None:
                async_dispatcher_send(
                    self.hass,
                    f"{SIGNAL_UPDATE_ENTITY}_{self.unique_id}_sensor",
                    self.longitude,
                )

            # If there are related entities we should update them too
            related_entities_sent = False
            if hasattr(self.hass.data.get(DOMAIN, {}), "entity_registry"):
                # Try to get entity registry from domain data
                for entry_id, data_item in self.hass.data[DOMAIN].items(): # renamed data to data_item
                    if hasattr(data_item, "entity_registry") and data_item.entity_registry:
                        entity_registry = data_item.entity_registry
                        if hasattr(entity_registry, "get_related_entities"):
                            related_entities = entity_registry.get_related_entities(self.unique_id)
                            for related_id in related_entities:
                                # Create a location payload for sensors
                                sensor_payload = {
                                    "value": self.latitude if "latitude" in related_id else self.longitude,
                                    "latitude": self.latitude,
                                    "longitude": self.longitude,
                                    "last_updated": dt_util.utcnow().isoformat()
                                }

                                async_dispatcher_send(
                                    self.hass,
                                    f"{SIGNAL_UPDATE_ENTITY}_{related_id}",
                                    sensor_payload,
                                )
                            related_entities_sent = True
                            break

            # If we didn't update via entity registry, try a more direct approach
            if not related_entities_sent and self.latitude is not None and self.longitude is not None:
                # Create a coordinates payload
                location_payload = {
                    "latitude": self.latitude,
                    "longitude": self.longitude,
                    "last_updated": dt_util.utcnow().isoformat()
                }

                # Dispatch to latitude/longitude sensors based on their name pattern
                lat_sensor_id = f"{self.unique_id}_latitude"
                lon_sensor_id = f"{self.unique_id}_longitude"

                async_dispatcher_send(
                    self.hass,
                    f"{SIGNAL_UPDATE_ENTITY}_{lat_sensor_id}",
                    location_payload,
                )

                async_dispatcher_send(
                    self.hass,
                    f"{SIGNAL_UPDATE_ENTITY}_{lon_sensor_id}",
                    location_payload,
                )
        except Exception as ex:
            _LOGGER.exception("Error updating related entities: %s", ex)

        self.async_write_ha_state()

    def _process_payload(self, payload: Any) -> None:
        """Process the payload and update coordinates."""
        try:
            current_time = time.time()
            coordinates_changed = False

            # If payload is a dictionary, extract coordinates directly
            if isinstance(payload, dict):
                if "latitude" in payload and "longitude" in payload:
                    try:
                        lat = float(payload["latitude"]) if payload["latitude"] else None
                        lon = float(payload["longitude"]) if payload["longitude"] else None

                        # Skip invalid coordinates (both exactly 0, which is unlikely to be a real position)
                        if lat == 0 and lon == 0:
                            _LOGGER.debug("Skipping 0,0 coordinates in payload: %s", payload)
                            return

                        # Validate coordinates - skip if out of valid range
                        if (lat is not None and lon is not None and
                            (-90 <= lat <= 90 and -180 <= lon <= 180)):

                            # Check if coordinates have changed significantly
                            if (self._prev_latitude is None or
                                self._prev_longitude is None or
                                abs(lat - self._prev_latitude) > 0.00001 or
                                abs(lon - self._prev_longitude) > 0.00001):

                                coordinates_changed = True
                                self._latitude = lat
                                self._longitude = lon
                                self._prev_latitude = lat
                                self._prev_longitude = lon

                            # Add accuracy if available
                            if "gps_accuracy" in payload:
                                self._attr_extra_state_attributes["gps_accuracy"] = payload["gps_accuracy"]
                                # Also add unit
                                if "gps_accuracy_unit" in payload:
                                    self._attr_extra_state_attributes["gps_accuracy_unit"] = payload["gps_accuracy_unit"]
                                else:
                                    self._attr_extra_state_attributes["gps_accuracy_unit"] = "m"  # Default unit

                            # Also update last_updated even if coordinates haven't changed
                            if "last_updated" in payload:
                                self._attr_extra_state_attributes["last_updated"] = payload["last_updated"]
                            else:
                                self._attr_extra_state_attributes["last_updated"] = dt_util.utcnow().isoformat()
                    except (ValueError, TypeError):
                        _LOGGER.debug("Invalid coordinates in payload: %s", payload)

            # If topic is for a single coordinate
            elif "latitude" in self._topic.lower() or "lat" in self._topic.lower():
                try:
                    lat = float(payload)
                    if -90 <= lat <= 90:
                        if self._prev_latitude is None or abs(lat - self._prev_latitude) > 0.00001:
                            coordinates_changed = True
                            self._latitude = lat
                            self._prev_latitude = lat
                except (ValueError, TypeError):
                    _LOGGER.warning("Invalid latitude value: %s", payload)

            elif "longitude" in self._topic.lower() or "long" in self._topic.lower() or "lon" in self._topic.lower() or "lng" in self._topic.lower():
                try:
                    lon = float(payload)
                    if -180 <= lon <= 180:
                        if self._prev_longitude is None or abs(lon - self._prev_longitude) > 0.00001:
                            coordinates_changed = True
                            self._longitude = lon
                            self._prev_longitude = lon
                except (ValueError, TypeError):
                    _LOGGER.warning("Invalid longitude value: %s", payload)

            # Only update the timestamp if coordinates have changed or
            # sufficient time has passed (to avoid unnecessary state updates)
            time_since_last_update = current_time - self._last_update_time

            if coordinates_changed or time_since_last_update > 30:
                self._last_update_time = current_time
                # Update timestamp attribute if not already done
                if isinstance(payload, dict) and "last_updated" not in payload:
                    self._attr_extra_state_attributes["last_updated"] = dt_util.utcnow().isoformat()

                if coordinates_changed:
                    _LOGGER.debug("Updated device tracker coordinates.")

            # Add sensible default for gps_accuracy if necessary
            if "gps_accuracy" not in self._attr_extra_state_attributes:
                self._attr_extra_state_attributes["gps_accuracy"] = 0
                self._attr_extra_state_attributes["gps_accuracy_unit"] = "m"  # Add unit

        except Exception as ex:
            _LOGGER.exception("Error processing payload: %s", ex)

    @property
    def latitude(self) -> Optional[float]:
        """Return latitude value."""
        return self._latitude

    @property
    def longitude(self) -> Optional[float]:
        """Return longitude value."""
        return self._longitude

    @property
    def source_type(self) -> SourceType:
        """Return the source type of the device tracker."""
        return self._source_type

    @property
    def icon(self) -> str:
        """Return the icon."""
        return "mdi:car-connected"
