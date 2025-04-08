"""Update dispatcher for OVMS integration."""
import logging
import time
from typing import Any, Dict, Optional, Set, List

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from ..const import (
    LOGGER_NAME,
    SIGNAL_UPDATE_ENTITY,
    DOMAIN,
)
from ..attribute_manager import AttributeManager

_LOGGER = logging.getLogger(LOGGER_NAME)

class UpdateDispatcher:
    """Dispatcher for coordinating updates between related entities."""

    def __init__(self, hass: HomeAssistant, entity_registry, attribute_manager: AttributeManager):
        """Initialize the update dispatcher."""
        self.hass = hass
        self.entity_registry = entity_registry
        self.attribute_manager = attribute_manager
        self.last_location_update = {}  # Track when location was last updated
        self.location_values = {}  # Store current location values

    def dispatch_update(self, topic: str, payload: Any) -> None:
        """Dispatch update to entities subscribed to a topic."""
        try:
            # Get the primary entity for this topic
            entity_id = self.entity_registry.get_entity_for_topic(topic)
            if not entity_id:
                _LOGGER.debug("No entity registered for topic: %s", topic)
                return

            # Get the entity type
            entity_type = self.entity_registry.get_entity_type(entity_id)

            # Update the primary entity
            self._update_entity(entity_id, payload)

            # Special handling for location topics
            if self._is_coordinate_topic(topic):
                self._handle_location_update(topic, entity_id, payload)

            # Special handling for version topics
            if "version" in topic.lower() or "m.version" in topic.lower():
                self._handle_version_update(topic, entity_id, payload)

            # Special handling for GPS quality topics
            if self._is_gps_quality_topic(topic):
                self._handle_gps_quality_update(topic, payload)

            # Update related entities
            related_entities = self.entity_registry.get_related_entities(entity_id)
            for related_id in related_entities:
                # Get relationship type to determine how to handle the update
                relationship_type = self.entity_registry.relationship_types.get((entity_id, related_id))

                if relationship_type == "location_sensor":
                    # Direct pass-through for location sensor pairs
                    self._update_entity(related_id, payload)
                elif relationship_type == "combined_tracker":
                    # For combined trackers, we need to update with all location data
                    self._update_combined_tracker(related_id)
                else:
                    # Default behavior for other relationships
                    self._update_entity(related_id, payload)

        except Exception as ex:
            _LOGGER.exception("Error dispatching update: %s", ex)

    def _update_entity(self, entity_id: str, payload: Any) -> None:
        """Update a single entity with new data."""
        try:
            # Dispatch the update signal
            signal = f"{SIGNAL_UPDATE_ENTITY}_{entity_id}"

            _LOGGER.debug("Dispatching update for %s", entity_id)
            async_dispatcher_send(self.hass, signal, payload)

        except Exception as ex:
            _LOGGER.exception("Error updating entity %s: %s", entity_id, ex)

    def _is_coordinate_topic(self, topic: str) -> bool:
        """Check if a topic is related to location coordinates for device tracker.

        Only latitude and longitude topics should be considered coordinate topics
        """
        if topic is None:
            return False

        # Define strict coordinate keywords - only these for coordinates
        coordinate_keywords = ["latitude", "lat", "longitude", "long", "lon", "lng"]

        # Convert topic to parts for more precise matching
        parts = topic.split('/')

        # Only match exact coordinate keywords, not any topic containing "gps"
        for keyword in coordinate_keywords:
            # Check for exact match in parts
            if any(part.lower() == keyword for part in parts):
                return True

            # Check in full topic path for exact coordinate matches
            if f"/p/{keyword}" in topic.lower() or f".p.{keyword}" in topic.lower():
                return True

        # For multi-part words like "v_p_latitude", we need additional check
        if any(part.lower().endswith("_latitude") or
               part.lower().endswith("_longitude") for part in parts):
            return True

        return False

    def _is_gps_quality_topic(self, topic: str) -> bool:
        """Check if a topic is related to GPS quality."""
        if topic is None:
            return False
        gps_keywords = ["gpssq", "gps_sq", "gpshdop", "gps_hdop"]
        return any(keyword in topic.lower() for keyword in gps_keywords)

    def _handle_location_update(self, topic: str, entity_id: str, payload: Any) -> None:
        """Handle updates to location topics."""
        try:
            now = dt_util.utcnow().timestamp()

            # Extract latitude/longitude values if applicable
            is_latitude = any(keyword in topic.lower() for keyword in ["latitude", "lat"])
            is_longitude = any(keyword in topic.lower() for keyword in ["longitude", "long", "lon", "lng"])

            # Update our location values cache
            if is_latitude:
                self.location_values["latitude"] = self._parse_coordinate(payload)
                self.last_location_update["latitude"] = now
            elif is_longitude:
                self.location_values["longitude"] = self._parse_coordinate(payload)
                self.last_location_update["longitude"] = now

            # Only update device trackers if we have both latitude and longitude
            if "latitude" in self.location_values and "longitude" in self.location_values:
                self._update_all_device_trackers()

        except Exception as ex:
            _LOGGER.exception("Error handling location update: %s", ex)

    def _handle_version_update(self, topic: str, entity_id: str, payload: str) -> None:
        """Handle updates to version topics with special priority."""
        try:
            # If this is a version topic, update the device info
            is_version_topic = any(ver_keyword in topic.lower() for ver_keyword in ["version", "m.version"])

            # Only update device info for main module version (not vehicle-specific versions)
            is_main_version = is_version_topic and not any(
                vehicle_prefix in topic.lower()
                for vehicle_prefix in ["xvu", "xmg", "xsq", "xnl"]  # Vehicle-specific prefixes
            )

            if is_version_topic:
                _LOGGER.info("Detected firmware version update: %s", payload)

                # Truncate very long version strings to avoid potential issues
                if payload and len(payload) > 255:
                    trimmed_payload = payload[:252] + "..."
                    _LOGGER.warning("Version string too long, truncating: %s -> %s", payload, trimmed_payload)
                    payload = trimmed_payload

                # Only update the device firmware version if this is the main module version
                if is_main_version:
                    # Get the vehicle_id from config
                    vehicle_id = None
                    for entry_id, data in self.hass.data[DOMAIN].items():
                        if "mqtt_client" in data:
                            config = data["mqtt_client"].config
                            if "vehicle_id" in config:
                                vehicle_id = config["vehicle_id"]
                                _LOGGER.debug("Found vehicle_id '%s' in config", vehicle_id)
                                break

                    # Find the device in the registry
                    from homeassistant.helpers import device_registry as dr
                    device_registry = dr.async_get(self.hass)

                    # Find OVMS device
                    device = None
                    for dev in device_registry.devices.values():
                        for identifier in dev.identifiers:
                            if identifier[0] == DOMAIN:
                                device = dev
                                _LOGGER.debug("Found OVMS device: %s", dev.name)
                                break
                        if device:
                            break

                    # Update device with version information
                    if device:
                        try:
                            device_registry.async_update_device(
                                device.id,
                                sw_version=payload
                            )
                            _LOGGER.debug("Updated device %s firmware version to %s", device.id, payload)
                        except Exception as ex:
                            _LOGGER.error("Failed to update device with version: %s", ex)
                            # Try an alternative approach
                            try:
                                # Use a simpler update call as a fallback
                                device_registry.async_update_device(
                                    device.id,
                                    sw_version=payload[:100]  # Use just first 100 chars as a fallback
                                )
                            except Exception:
                                _LOGGER.error("Failed to update device with shortened version too")
                    else:
                        _LOGGER.debug("No OVMS device found in registry to update version")

                # Ensure version topics have higher priority
                current_priority = self.entity_registry.priorities.get(topic, 0)
                if current_priority < 15:
                    self.entity_registry.priorities[topic] = 15
                    _LOGGER.debug("Increased priority for version topic: %s", topic)

        except Exception as ex:
            _LOGGER.exception("Error handling version update: %s", ex)

    def _handle_gps_quality_update(self, topic: str, payload: Any) -> None:
        """Handle updates to GPS quality topics and update device trackers."""
        try:
            # Process GPS quality information
            quality_value = self._parse_numeric_value(payload)

            if quality_value is not None:
                # Get GPS attributes using attribute manager
                attributes = self.attribute_manager.get_gps_attributes(topic, payload)

                if "gps_accuracy" in attributes:
                    # Update all device trackers with this GPS accuracy
                    device_trackers = self.entity_registry.get_entities_by_type("device_tracker")
                    for tracker_id in device_trackers:
                        # Create update payload with accuracy
                        quality_payload = {
                            "gps_accuracy": attributes["gps_accuracy"],
                            "gps_accuracy_unit": "m",  # Add proper unit
                            "last_updated": dt_util.utcnow().isoformat()
                        }
                        self._update_entity(tracker_id, quality_payload)

        except Exception as ex:
            _LOGGER.exception("Error handling GPS quality update: %s", ex)

    def _parse_coordinate(self, value: Any) -> Optional[float]:
        """Parse a coordinate value from various formats."""
        if value is None:
            return None

        try:
            # If it's already a float or int, return it
            if isinstance(value, (float, int)):
                return float(value)

            # Try to convert string to float
            if isinstance(value, str):
                return float(value.strip())

            # Other cases
            return None

        except (ValueError, TypeError):
            return None

    def _parse_numeric_value(self, value: Any) -> Optional[float]:
        """Parse a numeric value from various formats."""
        if value is None:
            return None

        try:
            # If it's already a float or int, return it
            if isinstance(value, (float, int)):
                return float(value)

            # Try to convert string to float
            if isinstance(value, str):
                return float(value.strip())

            return None

        except (ValueError, TypeError):
            return None

    def _update_all_device_trackers(self) -> None:
        """Update all device trackers with current location data."""
        try:
            # Find all device trackers
            device_trackers = self.entity_registry.get_entities_by_type("device_tracker")

            # Get GPS accuracy if available
            accuracy = None
            mqtt_client = None

            # Try to get the MQTT client from hass.data
            for entry_id, data in self.hass.data.get(DOMAIN, {}).items():
                if "mqtt_client" in data:
                    mqtt_client = data["mqtt_client"]
                    break

            if mqtt_client and hasattr(mqtt_client, "get_gps_accuracy"):
                # Get vehicle_id with fallback to empty string
                vehicle_id = getattr(mqtt_client, "config", {}).get("vehicle_id", "")
                accuracy = mqtt_client.get_gps_accuracy(vehicle_id)

            # Create payload with current location data
            payload = {
                "latitude": self.location_values.get("latitude"),
                "longitude": self.location_values.get("longitude"),
                "last_updated": dt_util.utcnow().isoformat(),
            }

            # Add accuracy if available
            if accuracy is not None:
                payload["gps_accuracy"] = accuracy
                payload["gps_accuracy_unit"] = "m"  # Add proper unit

            for tracker_id in device_trackers:
                # Only update the combined device tracker, not individual coordinate trackers
                topic = self.entity_registry.get_topic_for_entity(tracker_id)
                if topic == "combined_location":
                    self._update_entity(tracker_id, payload)

        except Exception as ex:
            _LOGGER.exception("Error updating device trackers: %s", ex)

    def _update_combined_tracker(self, tracker_id: str) -> None:
        """Update a combined device tracker with current location data."""
        try:
            # Get GPS accuracy if available
            accuracy = None
            mqtt_client = None

            # Try to get the MQTT client from hass.data
            for entry_id, data in self.hass.data.get(DOMAIN, {}).items():
                if "mqtt_client" in data:
                    mqtt_client = data["mqtt_client"]
                    break

            if mqtt_client and hasattr(mqtt_client, "get_gps_accuracy"):
                accuracy = mqtt_client.get_gps_accuracy()

            # Create payload with current location data
            payload = {
                "latitude": self.location_values.get("latitude"),
                "longitude": self.location_values.get("longitude"),
                "last_updated": dt_util.utcnow().isoformat(),
            }

            # Add accuracy if available
            if accuracy is not None:
                payload["gps_accuracy"] = accuracy
                payload["gps_accuracy_unit"] = "m"  # Add proper unit

            # Update the tracker
            self._update_entity(tracker_id, payload)

        except Exception as ex:
            _LOGGER.exception("Error updating combined tracker: %s", ex)
