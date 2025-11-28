"""Entity registry for OVMS integration."""
import logging
from typing import Dict, Any, Optional, List, Set

from ..const import LOGGER_NAME

_LOGGER = logging.getLogger(LOGGER_NAME)

class EntityRegistry:
    """Registry for tracking OVMS entities and their relationships."""

    def __init__(self):
        """Initialize the entity registry."""
        self.topics = {}  # Maps topic -> list of entity_ids (changed from single entity_id)
        self.entities = {}  # Maps entity_id -> entity_info
        self.relationships = {}  # Maps entity_id -> list of related entity_ids
        self.relationship_types = {}  # Maps (entity_id, related_id) -> relationship_type
        self.priorities = {}  # Maps (topic, entity_id) -> priority
        self.entity_types = {}  # Maps entity_id -> entity_type
        self.reverse_lookup = {}  # Maps entity_id -> topic

    def register_entity(self, topic: str, entity_id: str, entity_type: str, priority: int = 0) -> bool:
        """Register an entity for a topic with specified priority."""
        try:
            # Initialize topic list if needed
            if topic not in self.topics:
                self.topics[topic] = []

            # Check if this entity is already registered for this topic
            if entity_id in self.topics[topic]:
                _LOGGER.debug("Entity %s already registered for topic %s", entity_id, topic)
                return False

            # Add entity to the topic's list
            self.topics[topic].append(entity_id)
            self.entity_types[entity_id] = entity_type
            self.priorities[(topic, entity_id)] = priority
            self.reverse_lookup[entity_id] = topic

            # Initialize relationships
            if entity_id not in self.relationships:
                self.relationships[entity_id] = set()

            _LOGGER.debug("Registered %s for topic %s (priority %d)", entity_id, topic, priority)
            return True

        except Exception as ex:
            _LOGGER.exception("Error registering entity: %s", ex)
            return False

    def register_relationship(self, entity_id: str, related_id: str, relationship_type: str) -> None:
        """Register a relationship between two entities."""
        try:
            # Ensure both entities have relationship entries
            if entity_id not in self.relationships:
                self.relationships[entity_id] = set()

            if related_id not in self.relationships:
                self.relationships[related_id] = set()

            # Add the relationship
            self.relationships[entity_id].add(related_id)
            self.relationships[related_id].add(entity_id)

            # Store the relationship type
            self.relationship_types[(entity_id, related_id)] = relationship_type
            self.relationship_types[(related_id, entity_id)] = relationship_type

            _LOGGER.debug(
                "Registered %s relationship between %s and %s",
                relationship_type, entity_id, related_id
            )

        except Exception as ex:
            _LOGGER.exception("Error registering relationship: %s", ex)

    def get_entity_for_topic(self, topic: str) -> Optional[str]:
        """Get the primary entity ID associated with a topic (for backward compatibility).
        
        Returns the first entity if multiple are registered.
        """
        entities = self.topics.get(topic, [])
        return entities[0] if entities else None

    def get_entities_for_topic(self, topic: str) -> List[str]:
        """Get all entity IDs associated with a topic."""
        return self.topics.get(topic, [])

    def get_topic_for_entity(self, entity_id: str) -> Optional[str]:
        """Get the topic associated with an entity ID."""
        return self.reverse_lookup.get(entity_id)

    def get_related_entities(self, entity_id: str) -> Set[str]:
        """Get all entities related to the specified entity."""
        return self.relationships.get(entity_id, set())

    def get_related_entities_by_type(self, entity_id: str, relationship_type: str) -> List[str]:
        """Get entities related to the specified entity with the given relationship type."""
        related_entities = self.relationships.get(entity_id, set())
        return [
            related_id for related_id in related_entities
            if self.relationship_types.get((entity_id, related_id)) == relationship_type
        ]

    def get_entity_type(self, entity_id: str) -> Optional[str]:
        """Get the entity type for an entity ID."""
        return self.entity_types.get(entity_id)

    def update_entity_metadata(self, entity_id: str, metadata: Dict[str, Any]) -> None:
        """Update metadata for an entity."""
        if entity_id not in self.entities:
            self.entities[entity_id] = {}

        self.entities[entity_id].update(metadata)

    def get_entity_metadata(self, entity_id: str) -> Dict[str, Any]:
        """Get metadata for an entity."""
        return self.entities.get(entity_id, {})

    def get_entities_by_type(self, entity_type: str) -> List[str]:
        """Get all entities of a specific type."""
        return [
            entity_id for entity_id, etype in self.entity_types.items()
            if etype == entity_type
        ]

    def get_all_entities(self) -> List[str]:
        """Get all registered entity IDs."""
        return list(self.entity_types.keys())

    def get_entity_stats(self) -> Dict[str, int]:
        """Get statistics about registered entities by type."""
        stats = {}
        for entity_type in set(self.entity_types.values()):
            stats[entity_type] = len(self.get_entities_by_type(entity_type))
        return stats