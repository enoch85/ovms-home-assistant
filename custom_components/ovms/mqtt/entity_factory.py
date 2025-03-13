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

            # If it's a device tracker, use the special naming format
            if entity_type == "device_tracker":
                vehicle_id = self.config.get("vehicle_id", "")
                friendly_name = self.naming_service.create_device_tracker_name(vehicle_id)

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

            # For device trackers, also create a sensor version
            if entity_type == "device_tracker":
                await self._create_location_entities(topic, payload, entity_data)

            # Send to platform or queue for later
            if self.platforms_loaded:
                async_dispatcher_send(
                    self.hass,
                    SIGNAL_ADD_ENTITIES,
                    dispatcher_data,
                )
            else:
                await self.entity_queue.put(dispatcher_data)

        except Exception as ex:
            _LOGGER.exception("Error creating entity: %s", ex)

    async def _create_location_entities(self, topic: str, payload: str, entity_data: Dict[str, Any]) -> None:
        """Create sensor versions of location entities and coordinate their updates."""
        try:
            unique_id = entity_data.get("unique_id")
            name = entity_data.get("name")
            vehicle_id = self.config.get("vehicle_id", "")

            # Determine if this is latitude or longitude
            is_latitude = any(keyword in topic.lower() for keyword in ["latitude", "lat"])
            is_longitude = any(keyword in topic.lower() for keyword in ["longitude", "long", "lon", "lng"])

            # Track for the device tracker coordination
            location_type = "latitude" if is_latitude else "longitude" if is_longitude else "location"
            self.location_entities[location_type] = unique_id

            # Create a corresponding sensor entity
            sensor_unique_id = f"{unique_id}_sensor"
            sensor_name = f"{name}_sensor"

            # Make sure friendly name is also descriptive
            friendly_name = entity_data.get('friendly_name', name)
            sensor_friendly_name = f"{friendly_name} Sensor"

            # Prepare attributes for the sensor
            attributes = entity_data.get("attributes", {})
            category = attributes.get("category", "location")
            parts = entity_data.get("parts", [])
            sensor_attributes = self.attribute_manager.prepare_attributes(topic, category, parts)
            sensor_attributes.update({
                "original_entity": unique_id,
                "original_entity_type": "device_tracker",
                "location_type": location_type,
            })

            sensor_data = {
                "entity_type": "sensor",
                "unique_id": sensor_unique_id,
                "name": sensor_name,
                "friendly_name": sensor_friendly_name,
                "topic": topic,
                "payload": payload,
                "device_info": self._get_device_info(),
                "attributes": sensor_attributes,
            }

            # Register the relationship for update coordination
            self.entity_registry.register_relationship(
                unique_id,
                sensor_unique_id,
                "location_sensor"
            )

            # Add to entity registry
            self.entity_registry.register_entity(topic, sensor_unique_id, "sensor", priority=5)

            # Send to platform or queue for later
            if self.platforms_loaded:
                async_dispatcher_send(
                    self.hass,
                    SIGNAL_ADD_ENTITIES,
                    sensor_data,
                )
            else:
                await self.entity_queue.put(sensor_data)

            # If we have both latitude and longitude, create a combined device tracker
            if "latitude" in self.location_entities and "longitude" in self.location_entities:
                await self._create_combined_device_tracker()

        except Exception as ex:
            _LOGGER.exception("Error creating location entities: %s", ex)

    async def _create_combined_device_tracker(self) -> None:
        """Create a combined device tracker using lat/lon data."""
        try:
            vehicle_id = self.config.get("vehicle_id", "")
            if not vehicle_id:
                return

            # Create a unique ID for the combined device tracker
            tracker_id = f"{vehicle_id}_location"

            # Skip if already created
            if tracker_id in self.created_entities:
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

