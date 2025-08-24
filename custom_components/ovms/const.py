"""Constants for the OVMS integration."""
# Re-exported constants from Home Assistant for convenience
from homeassistant.const import (  # noqa: W0611
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    CONF_PROTOCOL,
)

DOMAIN = "ovms"
CONFIG_VERSION = 1

# Configuration
CONF_VEHICLE_ID = "vehicle_id"
CONF_QOS = "qos"
CONF_TOPIC_PREFIX = "topic_prefix"
CONF_CLIENT_ID = "client_id"
CONF_UNIT_SYSTEM = "unit_system"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_MQTT_USERNAME = "mqtt_username"
CONF_TOPIC_STRUCTURE = "topic_structure"
CONF_VERIFY_SSL = "verify_ssl"
CONF_ORIGINAL_VEHICLE_ID = "original_vehicle_id"
CONF_CREATE_CELL_SENSORS = "create_cell_sensors"  # Option to create individual cell sensors
CONF_TOPIC_BLACKLIST = "topic_blacklist"  # Option to blacklist topics
CONF_ENTITY_STALENESS_MANAGEMENT = "entity_staleness_management"  # Hours after which unavailable entities are hidden from UI to reduce clutter (history preserved)
CONF_DELETE_STALE_HISTORY = "delete_stale_history"  # Delete history when hiding stale entities

# Defaults
DEFAULT_PORT = 1883
DEFAULT_QOS = 1
DEFAULT_PROTOCOL = "mqtt"
DEFAULT_CLIENT_ID = "homeassistant_ovms"
DEFAULT_TOPIC_PREFIX = "ovms"
DEFAULT_SCAN_INTERVAL = 60
DEFAULT_UNIT_SYSTEM = "metric"
DEFAULT_TOPIC_STRUCTURE = "{prefix}/{mqtt_username}/{vehicle_id}"
DEFAULT_VERIFY_SSL = True
DEFAULT_CREATE_CELL_SENSORS = False  # Never create individual cell sensors by default

# System/Integration blacklist - patterns that are always filtered (developer controlled)
SYSTEM_TOPIC_BLACKLIST = [
    ".log", 
    "battery.log", 
    "power.log", 
    "gps.log", 
    "xrt.log",
    "event.system.modem.muxstart",
    "event.system.modem.netwait", 
    "event.system.modem.netstart",
    "event.system.modem.netmode",
    "event.system.modem.gotip"
]

# User customizable blacklist - additional patterns users can configure
DEFAULT_USER_TOPIC_BLACKLIST = []

# Combined default for initial setup
DEFAULT_TOPIC_BLACKLIST = SYSTEM_TOPIC_BLACKLIST + DEFAULT_USER_TOPIC_BLACKLIST
DEFAULT_ENTITY_STALENESS_MANAGEMENT = None  # Disabled by default - None means disabled, any number means enabled with that many hours
DEFAULT_DELETE_STALE_HISTORY = False  # Preserve history by default

# Options
PROTOCOLS = ["mqtt", "mqtts"]
UNIT_SYSTEMS = ["metric", "imperial"]

# Topic structure templates
TOPIC_STRUCTURES = [
    "{prefix}/{mqtt_username}/{vehicle_id}",  # ovms/username/vehicleid
    "{prefix}/client/{vehicle_id}",  # Traditional structure
    "{prefix}/{vehicle_id}",  # Simple structure
    "custom"  # Allow fully custom format
]

# MQTT Topics
TOPIC_WILDCARD = "#"
# Main subscription topic with structure variables
TOPIC_TEMPLATE = "{structure_prefix}/#"
# Discovery topic to find all OVMS topics
DISCOVERY_TOPIC = "{prefix}/#"
# Command topic template for request-response pattern
COMMAND_TOPIC_TEMPLATE = "{structure_prefix}/client/rr/command/{command_id}"
RESPONSE_TOPIC_TEMPLATE = "{structure_prefix}/client/rr/response/{command_id}"

# Logger
LOGGER_NAME = "custom_components.ovms"

# Category labels for grouping entities
CATEGORY_BATTERY = "battery"
CATEGORY_CHARGING = "charging"
CATEGORY_CLIMATE = "climate"
CATEGORY_DOOR = "door"
CATEGORY_LOCATION = "location"
CATEGORY_MOTOR = "motor"
CATEGORY_TRIP = "trip"
CATEGORY_DEVICE = "device"
CATEGORY_DIAGNOSTIC = "diagnostic"
CATEGORY_POWER = "power"
CATEGORY_NETWORK = "network"
CATEGORY_SYSTEM = "system"
CATEGORY_TIRE = "tire"
CATEGORY_VW_EUP = "vw_eup"
CATEGORY_SMART_FORTWO = "smart_fortwo"
CATEGORY_MG_ZS_EV = "mg_zs_ev"
CATEGORY_NISSAN_LEAF = "nissan_leaf"
CATEGORY_RENAULT_TWIZY = "renault_twizy"

# Signal constants
SIGNAL_ENTITY_DISCOVERY = f"{DOMAIN}_entity_discovery"
SIGNAL_TOPIC_UPDATE = f"{DOMAIN}_topic_update"
SIGNAL_ADD_ENTITIES = f"{DOMAIN}_add_entities"
SIGNAL_UPDATE_ENTITY = f"{DOMAIN}_update_entity"
SIGNAL_PLATFORMS_LOADED = f"{DOMAIN}_platforms_loaded"

# Error codes
ERROR_CANNOT_CONNECT = "cannot_connect"
ERROR_INVALID_AUTH = "invalid_auth"
ERROR_TIMEOUT = "timeout"
ERROR_INVALID_RESPONSE = "invalid_response"
ERROR_NO_TOPICS = "no_topics"
ERROR_TOPIC_ACCESS_DENIED = "topic_access_denied"
ERROR_TLS_ERROR = "tls_error"
ERROR_UNKNOWN = "unknown"

# Command rate limiting
DEFAULT_COMMAND_RATE_LIMIT = 5  # commands per minute
DEFAULT_COMMAND_RATE_PERIOD = 60.0  # seconds

# Maximum length for state values in Home Assistant
MAX_STATE_LENGTH = 255

def truncate_state_value(value, max_length=MAX_STATE_LENGTH):
    """Truncate state value to the maximum allowed length.

    Args:
        value: The state value to truncate
        max_length: Maximum allowed length (default: 255)

    Returns:
        Truncated value if needed, original value otherwise
    """
    if value is None:
        return None

    # Convert to string if not already
    if not isinstance(value, str):
        value = str(value)

    # Check length and truncate if needed
    if len(value) > max_length:
        return value[:max_length-3] + "..."

    return value
