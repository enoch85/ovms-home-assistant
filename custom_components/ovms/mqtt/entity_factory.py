"""Entity factory for OVMS integration."""
import asyncio
import logging
import hashlib
import re
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
        """Create one or more Home Assistant entities from OVMS topic data."""

        try:
            parts = entity_data.get("parts", [])
            raw_name = entity_data.get("raw_name", "")
            metric_info = entity_data.get("metric_info")
            base_entity_type = entity_data.get("entity_type")

            if not base_entity_type:
                _LOGGER.warning("No base entity type for topic: %s", topic)
                return
            
            # Generate base unique_id + friendly name
            entity_data = self._generate_unique_ids(topic, entity_data)
            unique_id = entity_data["unique_id"]

            # Naming service provides the display name
            friendly_name = self.naming_service.create_friendly_name(
                parts, metric_info, topic, raw_name
            )

            attributes = entity_data.get("attributes", {})
            category = attributes.get("category", "unknown")
            attributes = self.attribute_manager.prepare_attributes(
                topic, category, parts, metric_info
            )

            # Prepare the list of entities to create
            entities_to_create = []

            # ---- Base sensor / binary_sensor ----
            base_entity = {
                "entity_type": base_entity_type,
                "unique_id": unique_id,
                "name": entity_data.get("name"),
                "friendly_name": friendly_name,
                "topic": topic,
                "payload": payload,
                "device_info": self._get_device_info(),
                "attributes": attributes,
            }

            entities_to_create.append(base_entity)

            # If topic parser attached switch_info → create a second entity
            switch_info = entity_data.get("switch_info")
            if switch_info:
                switch_unique = f"{unique_id}_switch"
                switch_friendly = switch_info.get("name", f"{friendly_name}")

                switch_entity = {
                    "entity_type": "switch",
                    "unique_id": switch_unique,
                    "name": f"{entity_data.get('name')}_switch",
                    "friendly_name": switch_friendly,
                    "topic": topic,
                    "payload": payload,
                    "device_info": self._get_device_info(),
                    "attributes": attributes,
                    "on_command": switch_info.get("on_command"),
                    "off_command": switch_info.get("off_command"),
                }

                entities_to_create.append(switch_entity)

            # Coordinate tracking (lat/lon)
            if self._is_coordinate_entity(topic, entity_data):
                await self._track_coordinate_entity(topic, unique_id, entity_data)

            # Dispatch entities (immediately or queued)
            for ent in entities_to_create:
                ent_unique = ent["unique_id"]

                if ent_unique in self.created_entities:
                    continue

                self.created_entities.add(ent_unique)
                self.entity_registry.register_entity(
                    topic, ent_unique, ent["entity_type"], priority=entity_data.get("priority", 0)
                )

                if self.platforms_loaded:
                    async_dispatcher_send(self.hass, SIGNAL_ADD_ENTITIES, ent)
                else:
                    await self.entity_queue.put(ent)

            # If we have lat + lon → create combined device_tracker
            if (
                not self.combined_tracker_created
                and "latitude" in self.location_entities
                and "longitude" in self.location_entities
            ):
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
        vehicle_id = self.config.get("vehicle_id", "unknown").lower()
        topic_hash = hashlib.md5(topic.encode()).hexdigest()[:6]

        # Extract metric path from topic (everything after vehicle ID)
        topic_parts = topic.split('/')
        if len(topic_parts) >= 4:
            metric_path = '_'.join(topic_parts[3:])
            metric_path = re.sub(r'[^a-zA-Z0-9_]', '_', metric_path.lower())
            unique_id = f"ovms_{vehicle_id}_{metric_path}_{topic_hash}"
        else:
            unique_id = f"ovms_{vehicle_id}_{topic_hash}"

        entity_data["unique_id"] = unique_id
        return entity_data

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
