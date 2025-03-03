"""Constants for the OVMS MQTT integration."""
from typing import Dict, Final

# Domain
DOMAIN: Final = "ovms_mqtt"

# Configuration constants
CONF_TOPIC_PREFIX: Final = "topic_prefix"
DEFAULT_TOPIC_PREFIX: Final = "ovms"

CONF_VEHICLE_ID: Final = "vehicle_id"
DEFAULT_VEHICLE_ID: Final = "my_vehicle"

CONF_QOS: Final = "qos"
DEFAULT_QOS: Final = 0

# QoS options
QOS_OPTIONS: Final[Dict[int, str]] = {
    0: "0 - At most once (Fire and forget)",
    1: "1 - At least once (Acknowledged delivery)",
    2: "2 - Exactly once (Assured delivery)"
}

# SSL/TLS configuration options
CONF_TLS_INSECURE: Final = "tls_insecure"
DEFAULT_TLS_INSECURE: Final = False

CONF_CERTIFICATE_PATH: Final = "certificate_path"

# Entity availability configuration
CONF_AVAILABILITY_TIMEOUT: Final = "availability_timeout"
DEFAULT_AVAILABILITY_TIMEOUT: Final = 300  # 5 minutes in seconds

# Connection types
CONF_CONNECTION_TYPE: Final = "connection_type"
CONNECTION_TYPE_STANDARD: Final = "standard"
CONNECTION_TYPE_SECURE: Final = "secure"
CONNECTION_TYPE_WEBSOCKETS: Final = "websockets"
CONNECTION_TYPE_WEBSOCKETS_SECURE: Final = "websockets_secure"

CONNECTION_TYPES: Final[Dict[str, str]] = {
    CONNECTION_TYPE_STANDARD: "Standard MQTT (mqtt://)",
    CONNECTION_TYPE_SECURE: "Secure MQTT (mqtts://)",
    CONNECTION_TYPE_WEBSOCKETS: "WebSockets (ws://)",
    CONNECTION_TYPE_WEBSOCKETS_SECURE: "Secure WebSockets (wss://)"
}

# Default ports
DEFAULT_PORT: Final = 1883
DEFAULT_PORT_SSL: Final = 8883
DEFAULT_PORT_WS: Final = 9001
DEFAULT_PORT_WSS: Final = 9443

# Device information
DEFAULT_MANUFACTURER: Final = "Open Vehicle Monitoring System"
