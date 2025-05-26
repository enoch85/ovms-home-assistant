"""Simplified update dispatcher for OVMS integration."""
import logging
from typing import Any, Set

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from ..const import LOGGER_NAME, SIGNAL_UPDATE_ENTITY
from .topic_classifier import TopicClassifier

_LOGGER = logging.getLogger(LOGGER_NAME)


class UpdateDispatcher:
    """Simplified dispatcher for entity updates."""

    def __init__(self, hass: HomeAssistant, entity_registry, attribute_manager):
        """Initialize the update dispatcher."""
        self.hass = hass
        self.entity_registry = entity_registry
        self.attribute_manager = attribute_manager

    def dispatch_update(self, topic: str, payload: Any) -> None:
        """Dispatch update to all relevant entities."""
        try:
            # Get all entities that should receive this update
            entities_to_update = self._get_entities_for_topic(topic)
            
            if not entities_to_update:
                _LOGGER.debug("No entities registered for topic: %s", topic)
                return

            _LOGGER.debug("Updating %d entities for topic %s", len(entities_to_update), topic)

            # Send updates to all relevant entities
            for entity_id in entities_to_update:
                self._send_update(entity_id, payload)

        except Exception as ex:
            _LOGGER.exception("Error dispatching update for topic %s: %s", topic, ex)

    def _get_entities_for_topic(self, topic: str) -> Set[str]:
        """Get all entities that should receive updates for a topic."""
        entities = set()
        
        # Get primary entity registered for this exact topic
        primary_entity = self.entity_registry.get_entity_for_topic(topic)
        if primary_entity:
            entities.add(primary_entity)
        
        # For coordinate topics, add all device trackers
        if TopicClassifier.is_coordinate_topic(topic):
            device_trackers = self.entity_registry.get_entities_by_type("device_tracker")
            entities.update(device_trackers)
        
        # If no entities found, try to find related entities by base metric
        if not entities:
            base_metric = TopicClassifier.extract_base_metric(topic)
            all_entity_ids = self.entity_registry.get_all_entities()
            
            for entity_id in all_entity_ids:
                entity_topic = self.entity_registry.get_topic_for_entity(entity_id)
                if entity_topic and self._should_entity_receive_update(entity_topic, topic, base_metric):
                    entities.add(entity_id)
        
        return entities

    def _should_entity_receive_update(self, entity_topic: str, update_topic: str, base_metric: str) -> bool:
        """Check if entity should receive update from topic."""
        # Direct topic match
        if entity_topic == update_topic:
            return True
            
        # Base metric match - entities with same core metric should get updates
        entity_base = TopicClassifier.extract_base_metric(entity_topic)
        if entity_base and entity_base == base_metric:
            return True
                
        return False

    def _send_update(self, entity_id: str, payload: Any) -> None:
        """Send update signal to specific entity."""
        try:
            signal = f"{SIGNAL_UPDATE_ENTITY}_{entity_id}"
            async_dispatcher_send(self.hass, signal, payload)
        except Exception as ex:
            _LOGGER.exception("Error sending update to entity %s: %s", entity_id, ex)
