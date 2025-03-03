"""The OVMS MQTT integration."""
import asyncio
import json
import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.components import mqtt
from homeassistant.helpers import entity_registry as er
from homeassistant.const import (
    CONF_NAME,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_PORT,
)

from .const import (
    DOMAIN,
    CONF_TOPIC_PREFIX,
    DEFAULT_TOPIC_PREFIX,
    DEFAULT_QOS,
    CONF_VEHICLE_ID,
    DEFAULT_VEHICLE_ID,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OVMS MQTT from a config entry."""
    _LOGGER.debug("Setting up OVMS MQTT integration")
    
    # Initialize storage for entities
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "entities": {},
        "config": entry.data,
    }
    
    # Extract configuration
    topic_prefix = entry.data.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
    vehicle_id = entry.data.get(CONF_VEHICLE_ID, DEFAULT_VEHICLE_ID)

    # Verify MQTT is available
    if not mqtt.async_setup_entry(hass, entry):
        _LOGGER.error("Could not set up MQTT")
        return False

    async def message_received(msg):
        """Handle new MQTT messages."""
        topic = msg.topic
        payload = msg.payload
        
        # Debug log incoming messages
        _LOGGER.debug(f"Received message on topic {topic}: {payload}")
        
        # Process message
        try:
            # Try to decode JSON payload
            try:
                payload_data = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                # If not JSON, use raw payload as string
                try:
                    payload_data = {"value": payload.decode("utf-8")}
                except UnicodeDecodeError:
                    _LOGGER.warning(f"Could not decode payload for topic {topic}")
                    return
            
            # Extract entity ID from topic
            # Example: ovms/vehicle/battery/soc → ovms_vehicle_battery_soc
            topic_parts = topic.split('/')
            if len(topic_parts) < 2:
                _LOGGER.warning(f"Topic structure unexpected: {topic}")
                return
                
            # Create entity_id from topic
            entity_id = f"{DOMAIN}_{topic.replace('/', '_').lower()}"
            
            # Extract name from the last part of the topic
            name = topic_parts[-1].replace("_", " ").title()
            
            # Register or update entity
            await async_update_or_create_entity(hass, entry, topic, entity_id, name, payload_data)
            
        except Exception as e:
            _LOGGER.error(f"Error processing message from {topic}: {e}")

    # Subscribe to MQTT topics
    subscribe_topic = f"{topic_prefix}/{vehicle_id}/#"
    _LOGGER.debug(f"Subscribing to MQTT topic: {subscribe_topic}")
    
    unsub = await mqtt.async_subscribe(
        hass, subscribe_topic, message_received, DEFAULT_QOS
    )
    
    # Store unsubscribe function
    if "unsub" not in hass.data[DOMAIN]:
        hass.data[DOMAIN]["unsub"] = []
    hass.data[DOMAIN]["unsub"].append(unsub)
    
    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True


async def async_update_or_create_entity(hass, entry, topic, entity_id, name, payload_data):
    """Create or update sensor entity based on MQTT data."""
    # Get value and possible unit from payload
    if isinstance(payload_data, dict):
        # Try to find key with a value or state in the name
        value_key = next((k for k in payload_data.keys() if k in ["value", "state"]), None)
        if value_key:
            state_value = payload_data[value_key]
        else:
            # Just use the first value
            state_value = next(iter(payload_data.values())) if payload_data else None
        
        # Check for unit
        unit = payload_data.get("unit", "")
    else:
        state_value = payload_data
        unit = ""
    
    # Create unique ID
    unique_id = f"{DOMAIN}_{topic.replace('/', '_').lower()}"
    
    # Store or update entity
    if entry.entry_id not in hass.data[DOMAIN]:
        _LOGGER.error(f"Entry {entry.entry_id} not found in hass.data[{DOMAIN}]")
        return
        
    entities = hass.data[DOMAIN][entry.entry_id]["entities"]
    
    if entity_id not in entities:
        # Store new entity
        _LOGGER.debug(f"Creating new entity: {entity_id} from topic {topic}")
        entities[entity_id] = {
            "topic": topic,
            "state": state_value,
            "unit": unit,
            "name": name,
            "unique_id": unique_id,
        }
        
        # Signal platform to create entity
        async_dispatcher_send(hass, f"{DOMAIN}_{entry.entry_id}_new_entity", entity_id)
    else:
        # Update existing entity
        entities[entity_id]["state"] = state_value
        # Signal state update
        async_dispatcher_send(hass, f"{DOMAIN}_{entry.entry_id}_state_update", entity_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Unsubscribe from MQTT topics
    for unsub in hass.data[DOMAIN].get("unsub", []):
        unsub()
    
    # Remove entry data
    if entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok
