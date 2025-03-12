"""Update dispatcher for OVMS integration."""
import logging
from typing import Any, Dict, Optional, Set

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from ..const import (
    LOGGER_NAME,
    SIGNAL_UPDATE_ENTITY,
    DOMAIN,
)

_LOGGER = logging.getLogger(LOGGER_NAME)

class UpdateDispatcher:
    """Dispatcher for coordinating updates between related entities."""

    def __init__(self, hass: HomeAssistant, entity_registry):
        """Initialize the update dispatcher."""
        self.hass = hass
        self.entity_registry = entity_registry
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
            if self._is_location_topic(topic):
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

    def _is_location_topic(self, topic: str) -> bool:
        """Check if a topic is related to location data."""
        location_keywords = ["latitude", "longitude", "lat", "lon", "lng", "gps"]
        return any(keyword in topic.lower() for keyword in location_keywords)

    def _is_gps_quality_topic(self, topic: str) -> bool:
        """Check if a topic is related to GPS quality."""
        gps_keywords = ["gpssq", "gps_sq", "gpshdop", "gps_hdop"]
        return any(keyword in topic.lower() for keyword in gps_keywords)

    def _handle_location_update(self, topic: str, entity_id: str, payload: Any) -> None:
        """Handle updates to location topics."""
        try:
            now = dt_util.utcnow().timestamp()

            # Determine if this is latitude or longitude
            is_latitude = any(keyword in topic.lower() for keyword in ["latitude", "lat"])
            is_longitude = any(keyword in topic.lower() for keyword in ["longitude", "long", "lon", "lng"])

            if is_latitude:
                self.location_values["latitude"] = self._parse_coordinate(payload)
                self.last_location_update["latitude"] = now
            elif is_longitude:
                self.location_values["longitude"] = self._parse_coordinate(payload)
                self.last_location_update["longitude"] = now

            # Check if we have both coordinates and update combined tracker
            if "latitude" in self.location_values and "longitude" in self.location_values:
                self._update_all_device_trackers()

        except Exception as ex:
            _LOGGER.exception("Error handling location update: %s", ex)

    def _handle_gps_quality_update(self, topic: str, payload: Any) -> None:
        """Handle updates to GPS quality topics and update device trackers."""
        try:
            # Process GPS quality information
            quality_value = self._parse_numeric_value(payload)
            
            if quality_value is not None:
                # Check what type of GPS quality metric this is
                is_hdop = any(keyword in topic.lower() for keyword in ["gpshdop", "gps_hdop"])
                is_signal_quality = any(keyword in topic.lower() for keyword in ["gpssq", "gps_sq"])
                
                # Calculate accuracy
                accuracy = None
                if is_signal_quality:
                    # Signal quality (0-100) - higher is better
                    accuracy = max(5, 100 - quality_value)  # Minimum 5m accuracy
                elif is_hdop:
                    # HDOP - lower is better
                    accuracy = max(5, quality_value * 5)  # Each HDOP unit is ~5m of accuracy
                
                if accuracy is not None:
                    # Update all device trackers with this GPS accuracy
                    device_trackers = self.entity_registry.get_entities_by_type("device_tracker")
                    for tracker_id in device_trackers:
                        # Create update payload with accuracy
                        quality_payload = {
                            "gps_accuracy": accuracy,
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

            for tracker_id in device_trackers:
                # Skip if it's a specific lat/lon entity
                topic = self.entity_registry.get_topic_for_entity(tracker_id)
                if topic != "combined_location" and self._is_location_topic(topic):
                    continue

                # Update the combined tracker
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

            # Update the tracker
            self._update_entity(tracker_id, payload)

        except Exception as ex:
            _LOGGER.exception("Error updating combined tracker: %s", ex)

    def _handle_version_update(self, topic: str, entity_id: str, payload: str) -> None:
        """Handle updates to version topics with special priority."""
        try:
            # If this is the main version topic, keep it with higher priority
            if "m.version" in topic and not "xvu" in topic:
                # Update device info in Home Assistant with the version
                _LOGGER.info("Detected firmware version update: %s", payload)

                # Device registry will be updated by the entity class
                # Here we just ensure it has higher priority
                current_priority = self.entity_registry.priorities.get(topic, 0)
                if current_priority < 15:
                    self.entity_registry.priorities[topic] = 15
                    _LOGGER.debug("Increased priority for version topic: %s", topic)

        except Exception as ex:
            _LOGGER.exception("Error handling version update: %s", ex)
