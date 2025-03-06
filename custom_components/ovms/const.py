"""Constants for the OVMS integration."""
from homeassistant.const import (
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

# Options
PROTOCOLS = ["mqtt", "mqtts"]
UNIT_SYSTEMS = ["metric", "imperial"]

# Signal constants
SIGNAL_ENTITY_DISCOVERY = f"{DOMAIN}_entity_discovery"
SIGNAL_TOPIC_UPDATE = f"{DOMAIN}_topic_update"
SIGNAL_UPDATE_ENTITY = f"{DOMAIN}_update_entity"

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

# Signal constants
SIGNAL_ENTITY_DISCOVERY = f"{DOMAIN}_entity_discovery"
SIGNAL_TOPIC_UPDATE = f"{DOMAIN}_topic_update"

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
