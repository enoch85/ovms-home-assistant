"""Support for OVMS location tracking."""
import logging
import time
from typing import Any, Dict, Optional, List

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    LOGGER_NAME,
    SIGNAL_ADD_ENTITIES,
    SIGNAL_UPDATE_ENTITY
)

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

            tracker = OVMSDeviceTracker(
                data.get("unique_id", ""),
                data.get("name", ""),
                data.get("topic", ""),
                data.get("payload", {}),
                data.get("device_info", {}),
                data.get("attributes", {}),
                hass,
                data.get("friendly_name"),
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
        """Initialize the device tracker."""
        self._attr_unique_id = unique_id
        self._internal_name = name
        self._attr_name = friendly_name or name.replace("_", " ").title()
        self._topic = topic
        self._attr_device_info = device_info or {}
        self._attr_extra_state_attributes = attributes.copy() if attributes else {}
        if topic:
            self._attr_extra_state_attributes["topic"] = topic
        if "last_updated" not in self._attr_extra_state_attributes:
            self._attr_extra_state_attributes["last_updated"] = dt_util.utcnow().isoformat()

        self.hass = hass
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
        """Subscribe to updates."""
        await super().async_added_to_hass()

        # Restore previous state if available
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
            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_UPDATE_ENTITY}_{self.unique_id}",
                update_state,
            )
        )

    def _process_payload(self, payload: Any) -> None:
        """Process the payload and update coordinates."""
        try:
            current_time = time.time()
            coordinates_changed = False

            # If payload is a dictionary, extract coordinates directly
            if isinstance(payload, dict):
                if "latitude" in payload and "longitude" in payload:
                    try:
                        lat = float(payload["latitude"])
                        lon = float(payload["longitude"])

                        # Validate coordinates
                        if -90 <= lat <= 90 and -180 <= lon <= 180:
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

                            # Also update last_updated even if coordinates haven't changed
                            if "last_updated" in payload:
                                self._attr_extra_state_attributes["last_updated"] = payload["last_updated"]
                            else:
                                self._attr_extra_state_attributes["last_updated"] = dt_util.utcnow().isoformat()
                    except (ValueError, TypeError):
                        _LOGGER.warning("Invalid coordinates in payload: %s", payload)

            # If topic is for a single coordinate - we should never get in here,
            # but keeping for backward compatibility
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

            elif "longitude" in self._topic.lower() or "long" in self._topic.lower() or "lon" in self._topic.lower():
                try:
                    lon = float(payload)
                    if -180 <= lon <= 180:
                        if self._prev_longitude is None or abs(lon - self._prev_longitude) > 0.00001:
                            coordinates_changed = True
                            self._longitude = lon
                            self._prev_longitude = lon
                except (ValueError, TypeError):
                    _LOGGER.warning("Invalid longitude value: %s", payload)

            # Process specific GPS-related topics
            elif "gpshdop" in self._topic.lower():
                try:
                    value = float(payload) if payload else None
                    self._attr_extra_state_attributes["gps_hdop"] = value
                except (ValueError, TypeError):
                    pass
            elif "gpssq" in self._topic.lower():
                try:
                    value = float(payload) if payload else None
                    self._attr_extra_state_attributes["gps_signal_quality"] = value
                except (ValueError, TypeError):
                    pass
            elif "gpsspeed" in self._topic.lower():
                try:
                    value = float(payload) if payload else None
                    self._attr_extra_state_attributes["gps_speed"] = value
                except (ValueError, TypeError):
                    pass

            # Only update the timestamp if coordinates have changed or
            # sufficient time has passed (to avoid unnecessary state updates)
            time_since_last_update = current_time - self._last_update_time

            if coordinates_changed or time_since_last_update > 30:
                self._last_update_time = current_time
                # Update timestamp attribute if not already done
                if "last_updated" not in payload:
                    self._attr_extra_state_attributes["last_updated"] = dt_util.utcnow().isoformat()

                if coordinates_changed:
                    _LOGGER.debug("Updated device tracker coordinates.")

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
