#!/usr/bin/env python3
"""Test script to verify UpdateDispatcher fix for entity updates."""

import sys
import logging
from typing import Any, Dict, List, Optional, Set
from unittest.mock import Mock, MagicMock

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("test_update_dispatcher")

# Mock Home Assistant dependencies
class MockHomeAssistant:
    def __init__(self):
        self.data = {}

class MockEntityRegistry:
    def __init__(self):
        self.topics = {}  # Maps topic -> entity_id
        self.entity_types = {}  # Maps entity_id -> entity_type
        self.priorities = {}  # Maps topic -> priority
        self.reverse_lookup = {}  # Maps entity_id -> topic
        self.relationships = {}  # Maps entity_id -> set of related entity_ids
        self.relationship_types = {}  # Maps (entity_id, related_id) -> relationship_type

    def register_entity(self, topic: str, entity_id: str, entity_type: str, priority: int = 0) -> bool:
        """Register an entity for a topic."""
        self.topics[topic] = entity_id
        self.entity_types[entity_id] = entity_type
        self.priorities[topic] = priority
        self.reverse_lookup[entity_id] = topic
        if entity_id not in self.relationships:
            self.relationships[entity_id] = set()
        return True

    def get_entity_for_topic(self, topic: str) -> Optional[str]:
        """Get the entity ID associated with a topic."""
        return self.topics.get(topic)

    def get_topic_for_entity(self, entity_id: str) -> Optional[str]:
        """Get the topic associated with an entity ID."""
        return self.reverse_lookup.get(entity_id)

    def get_related_entities(self, entity_id: str) -> Set[str]:
        """Get all entities related to the specified entity."""
        return self.relationships.get(entity_id, set())

    def get_entities_by_type(self, entity_type: str) -> List[str]:
        """Get all entities of a specific type."""
        return [entity_id for entity_id, etype in self.entity_types.items() if etype == entity_type]

    def get_all_entities(self) -> List[str]:
        """Get all registered entity IDs."""
        return list(self.entity_types.keys())

class MockAttributeManager:
    def get_gps_attributes(self, topic: str, payload: Any) -> Dict[str, Any]:
        """Mock GPS attributes."""
        return {"gps_accuracy": 5.0}

def mock_async_dispatcher_send(hass, signal, payload):
    """Mock dispatcher send function."""
    logger.debug(f"MOCK DISPATCH: {signal} -> {payload}")

# Import and patch the real UpdateDispatcher
sys.path.insert(0, '/workspaces/ovms-home-assistant/custom_components/ovms/mqtt')

# Mock the Home Assistant imports
import sys
from unittest.mock import patch

# Create mock modules
mock_modules = [
    'homeassistant',
    'homeassistant.core',
    'homeassistant.helpers',
    'homeassistant.helpers.dispatcher',
    'homeassistant.util',
    'homeassistant.util.dt',
]

for module in mock_modules:
    if module not in sys.modules:
        sys.modules[module] = Mock()

# Mock specific functions
with patch.dict('sys.modules', {
    'homeassistant.helpers.dispatcher': Mock(async_dispatcher_send=mock_async_dispatcher_send),
    'homeassistant.util.dt': Mock(utcnow=Mock(return_value=Mock(timestamp=Mock(return_value=1234567890)))),
}):
    
    # Now import the real UpdateDispatcher
    from update_dispatcher import UpdateDispatcher

def test_entity_broadcasting():
    """Test that the fix correctly broadcasts updates to all relevant entities."""
    logger.info("=== Testing Entity Broadcasting Fix ===")
    
    # Create mock objects
    hass = MockHomeAssistant()
    entity_registry = MockEntityRegistry()
    attribute_manager = MockAttributeManager()
    
    # Create UpdateDispatcher
    dispatcher = UpdateDispatcher(hass, entity_registry, attribute_manager)
    
    # Mock the async_dispatcher_send function in the dispatcher
    dispatched_updates = []
    
    def mock_dispatch(signal, payload):
        dispatched_updates.append((signal, payload))
        logger.debug(f"Dispatched: {signal} -> {payload}")
    
    # Patch the _update_entity method to track dispatches
    original_update_entity = dispatcher._update_entity
    def tracked_update_entity(entity_id, payload):
        dispatched_updates.append((f"SIGNAL_UPDATE_ENTITY_{entity_id}", payload))
        logger.debug(f"Updated entity {entity_id} with payload: {payload}")
    
    dispatcher._update_entity = tracked_update_entity
    
    # Test Scenario 1: Multiple entities for same base topic
    logger.info("\n--- Test 1: Multiple entities for same topic ---")
    
    # Register multiple entities that should receive updates for same topic
    entity_registry.register_entity("ovms/mycar/v/p/latitude", "sensor.latitude_1", "sensor")
    entity_registry.register_entity("ovms/mycar/some_other_topic", "sensor.other", "sensor") 
    entity_registry.register_entity("combined_location", "device_tracker.car", "device_tracker")
    
    # Also register entities with topics that should match coordinate updates
    entity_registry.register_entity("ovms/mycar/v/p/longitude", "sensor.longitude_1", "sensor")
    
    # Clear dispatch history
    dispatched_updates.clear()
    
    # Dispatch an update for latitude
    dispatcher.dispatch_update("ovms/mycar/v/p/latitude", "45.123456")
    
    # Verify that multiple entities received the update
    logger.info(f"Total dispatches: {len(dispatched_updates)}")
    for signal, payload in dispatched_updates:
        logger.info(f"  - {signal}: {payload}")
    
    # Check that coordinate entities and device tracker received updates
    latitude_updates = [d for d in dispatched_updates if "latitude" in d[0] or "device_tracker" in d[0]]
    logger.info(f"Latitude-related updates: {len(latitude_updates)}")
    
    assert len(latitude_updates) >= 2, f"Expected at least 2 updates (latitude sensor + device tracker), got {len(latitude_updates)}"
    
    # Test Scenario 2: Derived topics
    logger.info("\n--- Test 2: Derived topics from same base metric ---")
    
    # Register entities with topics derived from same base metric
    entity_registry.register_entity("ovms/mycar/v/b/soc", "sensor.soc_primary", "sensor")
    entity_registry.register_entity("ovms/othercar/v/b/soc", "sensor.soc_other", "sensor") # Different vehicle, same metric
    
    dispatched_updates.clear()
    
    # Dispatch update for one vehicle's SOC
    dispatcher.dispatch_update("ovms/mycar/v/b/soc", "85.5")
    
    logger.info(f"SOC update dispatches: {len(dispatched_updates)}")
    for signal, payload in dispatched_updates:
        logger.info(f"  - {signal}: {payload}")
    
    # Should at least update the primary entity
    soc_updates = [d for d in dispatched_updates if "soc" in d[0]]
    assert len(soc_updates) >= 1, f"Expected at least 1 SOC update, got {len(soc_updates)}"
    
    # Test Scenario 3: Helper methods
    logger.info("\n--- Test 3: Helper methods ---")
    
    # Test _get_entities_for_topic
    entities_for_lat = dispatcher._get_entities_for_topic("ovms/mycar/v/p/latitude")
    logger.info(f"Entities for latitude topic: {entities_for_lat}")
    assert len(entities_for_lat) >= 2, f"Expected multiple entities for latitude, got {entities_for_lat}"
    
    # Test _should_entity_receive_topic_update
    should_receive_coord = dispatcher._should_entity_receive_topic_update("combined_location", "ovms/mycar/v/p/latitude")
    logger.info(f"Should combined_location receive latitude updates: {should_receive_coord}")
    assert should_receive_coord, "Device tracker should receive coordinate updates"
    
    # Test _extract_base_metric_path
    base_path = dispatcher._extract_base_metric_path("ovms/mycar/v/b/soc")
    logger.info(f"Base metric path for 'ovms/mycar/v/b/soc': {base_path}")
    assert base_path == "v/b/soc", f"Expected 'v/b/soc', got '{base_path}'"
    
    # Test coordinate topic detection
    is_coord = dispatcher._is_coordinate_topic("ovms/mycar/v/p/latitude")
    logger.info(f"Is latitude a coordinate topic: {is_coord}")
    assert is_coord, "Latitude should be detected as coordinate topic"
    
    logger.info("\n=== All tests passed! The fix appears to be working correctly. ===")

def test_before_and_after_behavior():
    """Compare behavior before and after the fix."""
    logger.info("\n=== Testing Before vs After Fix Behavior ===")
    
    # Simulate the OLD behavior (one entity per topic)
    logger.info("\n--- OLD Behavior Simulation ---")
    hass = MockHomeAssistant()
    entity_registry = MockEntityRegistry()
    
    # Register entities
    entity_registry.register_entity("ovms/mycar/v/b/soc", "sensor.soc", "sensor")
    entity_registry.register_entity("ovms/mycar/v/p/latitude", "sensor.latitude", "sensor")
    entity_registry.register_entity("combined_location", "device_tracker.car", "device_tracker")
    
    # OLD way: only get single entity for topic
    old_entity = entity_registry.get_entity_for_topic("ovms/mycar/v/b/soc")
    logger.info(f"OLD: Single entity for SOC topic: {old_entity}")
    
    # NEW behavior with our fix
    logger.info("\n--- NEW Behavior with Fix ---")
    attribute_manager = MockAttributeManager()
    dispatcher = UpdateDispatcher(hass, entity_registry, attribute_manager)
    
    # NEW way: get all entities that should receive updates
    new_entities = dispatcher._get_entities_for_topic("ovms/mycar/v/b/soc")
    logger.info(f"NEW: All entities for SOC topic: {new_entities}")
    
    logger.info(f"\nImprovement: {len(new_entities)} entities will receive updates vs {1 if old_entity else 0} before")

if __name__ == "__main__":
    try:
        test_entity_broadcasting()
        test_before_and_after_behavior()
        logger.info("\n🎉 All tests completed successfully! The UpdateDispatcher fix is working correctly.")
    except Exception as ex:
        logger.error(f"❌ Test failed: {ex}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
