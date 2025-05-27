"""Entity factory for OVMS integration."""
import asyncio
import logging
import hashlib
import uuid
from typing import Dict, Any, Optional, List

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from ..const import (
    DOMAIN,
    LOGGER_NAME,
    SIGNAL_ADD_ENTITIES,
)
from ..naming_service import EntityNamingService
from ..attribute_manager import AttributeManager
from ..metrics import get_metric_by_path, get_metric_by_pattern

_LOGGER = logging.getLogger(LOGGER_NAME)

class EntityFactory:
    """Factory for creating OVMS entities."""

    def __init__(self, hass: HomeAssistant, entity_registry, update_dispatcher, config: Dict[str, Any],
                naming_service: EntityNamingService, attribute_manager: AttributeManager):
        """Initialize the entity factory."""
        self.hass = hass
        self.entity_registry = entity_registry
        self.update_dispatcher = update_dispatcher
        self.config = config
        self.naming_service = naming_service
        self.attribute_manager = attribute_manager
        self.entity_queue = asyncio.Queue()
        self.platforms_loaded = False
        self.created_entities = set()
        self.location_entities = {}  # Track location-related entities
        self.combined_tracker_created = False  # Track if the combined tracker is created

    async def async_create_entities(self, topic: str, payload: str, entity_data: Dict[str, Any]) -> None:
        """Create entities based on parsed topic data."""
        try:
            entity_type = entity_data.get("entity_type")
            if not entity_type:
                return

            # Generate unique IDs
            entity_data = self._generate_unique_ids(topic, entity_data)

            # Check if we already processed this entity
            unique_id = entity_data.get("unique_id")
            if not unique_id:
                _LOGGER.error("No unique_id generated for topic: %s", topic)
                return
            if unique_id in self.created_entities:
                _LOGGER.debug("Entity already created for topic: %s", topic)
                return

            # Get parts and metric info
            parts = entity_data.get("parts", [])
            raw_name = entity_data.get("raw_name", "")
            metric_info = entity_data.get("metric_info")

            # Create friendly name using the naming service
            friendly_name = self.naming_service.create_friendly_name(
                parts, metric_info, topic, raw_name
            )

            _LOGGER.info("Creating %s: %s", entity_type, friendly_name)

            # Record that we've processed this entity
            self.created_entities.add(unique_id)

            # Store in entity registry
            priority = entity_data.get("priority", 0)
            self.entity_registry.register_entity(topic, unique_id, entity_type, priority)

            # Prepare attributes
            attributes = entity_data.get("attributes", {})
            category = attributes.get("category", "unknown")
            attributes = self.attribute_manager.prepare_attributes(topic, category, parts, metric_info)

            # Create entity data for dispatcher
            dispatcher_data = {
                "entity_type": entity_type,
                "unique_id": unique_id,
                "name": entity_data.get("name"),
                "friendly_name": friendly_name,
                "topic": topic,
                "payload": payload,
                "device_info": self._get_device_info(),
                "attributes": attributes,
            }

            # Check if this is a coordinate entity to track for the device tracker
            is_coordinate = self._is_coordinate_entity(topic, entity_data)
            if is_coordinate:
                await self._track_coordinate_entity(topic, unique_id, entity_data)

            # Send to platform or queue for later
            if self.platforms_loaded:
                async_dispatcher_send(
                    self.hass,
                    SIGNAL_ADD_ENTITIES,
                    dispatcher_data,
                )
            else:
                await self.entity_queue.put(dispatcher_data)

            # If we have both latitude and longitude entities tracked, create a combined device tracker
            if (len(self.location_entities) >= 2 and
                "latitude" in self.location_entities and
                "longitude" in self.location_entities and
                not self.combined_tracker_created):
                await self._create_combined_device_tracker()

        except Exception as ex:
            _LOGGER.exception("Error creating entity: %s", ex)

    def _is_coordinate_entity(self, topic: str, entity_data: Dict[str, Any]) -> bool:
        """Check if this entity contains coordinate data (latitude/longitude)."""
        topic_lower = topic.lower()
        name = entity_data.get("name", "").lower()

        # Check for latitude/longitude keywords
        if any(keyword in topic_lower or keyword in name
               for keyword in ["latitude", "lat", "longitude", "long", "lon", "lng"]):

            # More specific checks to avoid false positives
            parts = topic.split('/')
            for part in parts:
                part_lower = part.lower()
                if part_lower in ["latitude", "lat", "longitude", "long", "lon", "lng"]:
                    return True

            # Check for common patterns in topic paths
            if any(pattern in topic_lower for pattern in ["/p/lat", "/p/lon", ".p.lat", ".p.lon"]):
                return True

        return False

    async def _track_coordinate_entity(self, topic: str, unique_id: str, entity_data: Dict[str, Any]) -> None:
        """Track a coordinate entity for use in the combined device tracker."""
        try:
            # Determine if this is latitude or longitude
            is_latitude = any(keyword in topic.lower() for keyword in ["latitude", "lat"])
            is_longitude = any(keyword in topic.lower() for keyword in ["longitude", "long", "lon", "lng"])

            # Track the entity ID for later use in creating the combined tracker
            if is_latitude:
                self.location_entities["latitude"] = unique_id
                _LOGGER.debug("Tracked latitude entity: %s", unique_id)
            elif is_longitude:
                self.location_entities["longitude"] = unique_id
                _LOGGER.debug("Tracked longitude entity: %s", unique_id)

        except Exception as ex:
            _LOGGER.exception("Error tracking coordinate entity: %s", ex)

    async def _create_combined_device_tracker(self) -> None:
        """Create a combined device tracker using lat/lon data."""
        try:
            vehicle_id = self.config.get("vehicle_id", "")
            if not vehicle_id:
                return

            # Check if already created to avoid duplicates
            if self.combined_tracker_created:
                _LOGGER.debug("Combined tracker already created, skipping")
                return

            # Flag that we've created it
            self.combined_tracker_created = True

            # Create a unique ID for the combined device tracker
            tracker_id = f"{vehicle_id}_location"

            # Skip if already created
            if tracker_id in self.created_entities:
                _LOGGER.debug("Combined tracker entity already exists, skipping creation")
                return

            self.created_entities.add(tracker_id)

            # Create friendly name using the naming service
            friendly_name = self.naming_service.create_device_tracker_name(vehicle_id)

            # Create device tracker attributes
            attributes = self.attribute_manager.prepare_attributes(
                "combined_location", "location", []
            )
            attributes.update({
                "lat_entity_id": self.location_entities.get("latitude"),
                "lon_entity_id": self.location_entities.get("longitude"),
            })

            # Create device tracker data
            tracker_data = {
                "entity_type": "device_tracker",
                "unique_id": tracker_id,
                "name": f"ovms_{vehicle_id}_location",
                "friendly_name": friendly_name,
                "topic": "combined_location",  # Virtual topic
                "payload": {
                    "latitude": 0,
                    "longitude": 0,
                },
                "device_info": self._get_device_info(),
                "attributes": attributes,
            }

            # Register relationships with individual lat/lon entities
            if "latitude" in self.location_entities:
                self.entity_registry.register_relationship(
                    self.location_entities["latitude"],
                    tracker_id,
                    "combined_tracker"
                )

            if "longitude" in self.location_entities:
                self.entity_registry.register_relationship(
                    self.location_entities["longitude"],
                    tracker_id,
                    "combined_tracker"
                )

            # Add to entity registry
            self.entity_registry.register_entity("combined_location", tracker_id, "device_tracker", priority=10)

            # Send to platform or queue for later
            if self.platforms_loaded:
                async_dispatcher_send(
                    self.hass,
                    SIGNAL_ADD_ENTITIES,
                    tracker_data,
                )
            else:
                await self.entity_queue.put(tracker_data)

            _LOGGER.info("Created combined device tracker: %s", tracker_id)

        except Exception as ex:
            _LOGGER.exception("Error creating combined device tracker: %s", ex)

    def _generate_unique_ids(self, topic: str, entity_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate unique IDs for entities."""
        try:
            # Extract necessary parts
            entity_type = entity_data.get("entity_type")
            name = entity_data.get("name", "")
            vehicle_id = self.config.get("vehicle_id", "").lower()

            # Create a hash of the topic for uniqueness
            topic_hash = hashlib.md5(topic.encode()).hexdigest()[:8]

            # Extract category from attributes
            category = entity_data.get("attributes", {}).get("category", "unknown")

            # Create a unique ID
            unique_id = f"{vehicle_id}_{category}_{name}_{topic_hash}"

            # Update entity data
            updated_data = entity_data.copy()
            updated_data["unique_id"] = unique_id

            return updated_data

        except Exception as ex:
            _LOGGER.exception("Error generating unique IDs: %s", ex)
            # Fallback to a simple unique ID
            return {
                **entity_data,
                "unique_id": str(uuid.uuid4()),
            }

    def _get_device_info(self) -> Dict[str, Any]:
        """Get device info for the OVMS module."""
        try:
            vehicle_id = self.config.get("vehicle_id")

            return {
                "identifiers": {(DOMAIN, vehicle_id)},
                "name": f"OVMS - {vehicle_id}",
                "manufacturer": "Open Vehicles",
                "model": "OVMS Module",
                "sw_version": "Unknown",  # Will be updated when version is received
            }
        except Exception as ex:
            _LOGGER.exception("Error getting device info: %s", ex)
            # Return minimal device info
            return {
                "identifiers": {
                    (DOMAIN, self.config.get("vehicle_id", "unknown"))
                },
                "name": f"OVMS - {self.config.get('vehicle_id', 'unknown')}",
            }

    def _get_metric_path_from_topic(self, topic: str) -> str:
        """Extract metric path from topic."""
        topic_suffix = topic
        if topic.count('/') >= 3:  # Skip the prefix part
            parts = topic.split('/')
            # Find where the actual metric path starts
            for i, part in enumerate(parts):
                if part in ["metric", "status", "notify", "command", "m", "v", "s", "t"]:
                    topic_suffix = '/'.join(parts[i:])
                    break

        return topic_suffix.replace("/", ".")

    async def async_process_queued_entities(self) -> None:
        """Process any queued entities."""
        self.platforms_loaded = True

        queued_count = self.entity_queue.qsize()
        _LOGGER.info("Processing %d queued entities", queued_count)

        # Process all queued entities
        while not self.entity_queue.empty():
            entity_data = await self.entity_queue.get()
            _LOGGER.debug("Processing queued entity: %s", entity_data.get("name"))

            async_dispatcher_send(
                self.hass,
                SIGNAL_ADD_ENTITIES,
                entity_data,
            )

            self.entity_queue.task_done()
