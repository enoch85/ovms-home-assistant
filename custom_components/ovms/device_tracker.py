"""Support for OVMS location tracking."""

import logging
import time
from typing import Any, Dict, Optional

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN,
    LOGGER_NAME,
    SIGNAL_UPDATE_ENTITY,
    get_add_entities_signal,
)
from .naming_service import EntityNamingService
from .attribute_manager import AttributeManager
from .utils import get_merged_config

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

            _LOGGER.info(
                "Adding device tracker: %s",
                data.get("friendly_name", data.get("name", "unknown")),
            )

            # Create naming and attribute services - merge options with data
            config = get_merged_config(entry)
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
                attribute_manager,
            )

            async_add_entities([tracker])
        except Exception as ex:
            _LOGGER.exception("Error adding device tracker: %s", ex)

    # Subscribe to discovery events
    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            get_add_entities_signal(entry.entry_id),
            async_add_device_tracker,
        )
    )


class OVMSDeviceTracker(TrackerEntity, RestoreEntity):
    """OVMS Device Tracker Entity."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:car-connected"

    @property
    def force_update(self) -> bool:
        """Disable force-update to suppress recorder writes on unchanged state.

        TrackerEntity.force_update returns ``not self.should_poll`` (= True),
        which forces every async_write_ha_state() call to fire a state_changed
        event even when lat/lon haven't moved.  That creates redundant history
        entries that make the map track appear blocky.

        By returning False the state machine still updates its in-memory state
        and attributes, but only fires state_changed when something actually
        differs from the previous write.
        """
        return False

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
        naming_service: Optional[EntityNamingService] = None,
        attribute_manager: Optional[AttributeManager] = None,
    ) -> None:
        """Initialize the device tracker."""
        self._attr_unique_id = unique_id
        self._internal_name = name

        # Use services if provided, otherwise create internal defaults
        self.naming_service = naming_service or EntityNamingService({})
        self.attribute_manager = attribute_manager or AttributeManager({})

        self._attr_name = friendly_name or name.replace("_", " ").title()

        self._topic = topic
        self._attr_device_info = device_info if device_info else None

        # Process attributes
        self._attr_extra_state_attributes = attributes.copy() if attributes else {}

        # Ensure topic is present
        if topic:
            self._attr_extra_state_attributes["topic"] = topic

        self.hass = hass
        self._latitude = None
        self._longitude = None
        self._attr_location_accuracy = 0
        self._last_update_time = 0
        self._prev_latitude = None
        self._prev_longitude = None

        # Process initial payload
        if initial_payload:
            self._process_payload(initial_payload)

    async def async_added_to_hass(self) -> None:
        """Subscribe to updates and sync with related sensors."""
        await super().async_added_to_hass()

        # Restore previous state if available
        if (state := await self.async_get_last_state()) is not None:
            if state.attributes:
                # Restore coordinates
                if "latitude" in state.attributes:
                    self._latitude = state.attributes["latitude"]
                    self._prev_latitude = state.attributes["latitude"]
                if "longitude" in state.attributes:
                    self._longitude = state.attributes["longitude"]
                    self._prev_longitude = state.attributes["longitude"]
                if "gps_accuracy" in state.attributes:
                    try:
                        self._attr_location_accuracy = int(
                            state.attributes["gps_accuracy"]
                        )
                    except (ValueError, TypeError):
                        pass

                # Only restore our own custom attributes (inclusion list)
                _restorable = {"topic"}
                for key in _restorable:
                    if key in state.attributes:
                        self._attr_extra_state_attributes[key] = state.attributes[key]

        @callback
        def update_state(payload: Any) -> None:
            """Update the tracker state."""
            state_changed = self._process_payload(payload)

            # Process any JSON attributes if applicable
            if isinstance(payload, str):
                self._attr_extra_state_attributes = (
                    self.attribute_manager.process_json_payload(
                        payload, self._attr_extra_state_attributes
                    )
                )

            # Only write state when something meaningful changed.
            # The dispatcher already updates individual lat/lon sensor
            # entities directly via their own topic subscriptions.
            if state_changed:
                self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_UPDATE_ENTITY}_{self.unique_id}",
                update_state,
            )
        )

    def _process_payload(self, payload: Any) -> bool:
        """Process the payload and update coordinates.

        Returns True if state changed meaningfully (coordinates or accuracy).
        """
        try:
            current_time = time.time()
            coordinates_changed = False
            accuracy_changed = False

            # If payload is a dictionary, extract coordinates directly
            if isinstance(payload, dict):
                if "latitude" in payload and "longitude" in payload:
                    try:
                        lat = (
                            float(payload["latitude"]) if payload["latitude"] else None
                        )
                        lon = (
                            float(payload["longitude"])
                            if payload["longitude"]
                            else None
                        )

                        # Skip invalid coordinates (both exactly 0, which is unlikely to be a real position)
                        if lat == 0 and lon == 0:
                            _LOGGER.debug(
                                "Skipping 0,0 coordinates in payload: %s", payload
                            )
                            return False

                        # Validate coordinates - skip if out of valid range
                        if (
                            lat is not None
                            and lon is not None
                            and (-90 <= lat <= 90 and -180 <= lon <= 180)
                        ):

                            # Check if coordinates have changed significantly
                            if (
                                self._prev_latitude is None
                                or self._prev_longitude is None
                                or abs(lat - self._prev_latitude) > 0.00001
                                or abs(lon - self._prev_longitude) > 0.00001
                            ):

                                coordinates_changed = True
                                self._latitude = lat
                                self._longitude = lon
                                self._prev_latitude = lat
                                self._prev_longitude = lon

                    except (ValueError, TypeError):
                        _LOGGER.debug("Invalid coordinates in payload: %s", payload)

                # Process GPS accuracy from any dict payload (including standalone).
                # Maps to HA TrackerEntity.location_accuracy via _attr_location_accuracy.
                if "gps_accuracy" in payload:
                    try:
                        new_accuracy = int(payload["gps_accuracy"])
                        if new_accuracy != self._attr_location_accuracy:
                            self._attr_location_accuracy = new_accuracy
                            accuracy_changed = True
                    except (ValueError, TypeError):
                        pass

            # If topic is for a single coordinate
            elif "latitude" in self._topic.lower() or "lat" in self._topic.lower():
                try:
                    lat = float(payload)
                    if -90 <= lat <= 90:
                        if (
                            self._prev_latitude is None
                            or abs(lat - self._prev_latitude) > 0.00001
                        ):
                            coordinates_changed = True
                            self._latitude = lat
                            self._prev_latitude = lat
                except (ValueError, TypeError):
                    _LOGGER.warning("Invalid latitude value: %s", payload)

            elif (
                "longitude" in self._topic.lower()
                or "long" in self._topic.lower()
                or "lon" in self._topic.lower()
                or "lng" in self._topic.lower()
            ):
                try:
                    lon = float(payload)
                    if -180 <= lon <= 180:
                        if (
                            self._prev_longitude is None
                            or abs(lon - self._prev_longitude) > 0.00001
                        ):
                            coordinates_changed = True
                            self._longitude = lon
                            self._prev_longitude = lon
                except (ValueError, TypeError):
                    _LOGGER.warning("Invalid longitude value: %s", payload)

            # Only update the timestamp if coordinates have changed
            if coordinates_changed:
                self._last_update_time = current_time
                _LOGGER.debug("Updated device tracker coordinates.")

            return coordinates_changed or accuracy_changed

        except Exception as ex:
            _LOGGER.exception("Error processing payload: %s", ex)
            return False

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
        return SourceType.GPS
