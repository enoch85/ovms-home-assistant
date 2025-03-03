"""Constants for the OVMS MQTT integration."""

DOMAIN = "ovms_mqtt"

# Connection configuration
CONF_BROKER = "broker"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SSL = "ssl"
CONF_TOPIC_PREFIX = "topic_prefix"
CONF_VEHICLE_ID = "vehicle_id"
CONF_QOS = "qos"
CONF_CONNECTION_TYPE = "connection_type"
CONF_TLS_INSECURE = "tls_insecure"
CONF_CERTIFICATE_PATH = "certificate_path"
CONF_AVAILABILITY_TIMEOUT = "availability_timeout"

# Default values
DEFAULT_TOPIC_PREFIX = "ovms"
DEFAULT_VEHICLE_ID = "my_vehicle"
DEFAULT_QOS = 1
DEFAULT_PORT = 1883
DEFAULT_PORT_SSL = 8883
DEFAULT_PORT_WS = 80
DEFAULT_PORT_WSS = 443
DEFAULT_TLS_INSECURE = False
DEFAULT_AVAILABILITY_TIMEOUT = 120

# Connection types
CONNECTION_TYPE_STANDARD = "standard"
CONNECTION_TYPE_SECURE = "secure"
CONNECTION_TYPE_WEBSOCKETS = "websockets"
CONNECTION_TYPE_WEBSOCKETS_SECURE = "websockets_secure"

CONNECTION_TYPES = {
    CONNECTION_TYPE_STANDARD: "Standard MQTT",
    CONNECTION_TYPE_SECURE: "Secure MQTT (TLS)",
    CONNECTION_TYPE_WEBSOCKETS: "MQTT over WebSockets",
    CONNECTION_TYPE_WEBSOCKETS_SECURE: "MQTT over Secure WebSockets",
}

# QoS options
QOS_OPTIONS = {
    0: "At most once (0)",
    1: "At least once (1)",
    2: "Exactly once (2)",
}

# Known OVMS topics (static list with examples)
KNOWN_TOPICS = [
    "ovms/ovms-mqtt-ggk97e/GGK97E/metric/xvu/c/ac/p",
    "ovms/ovms-mqtt-ggk97e/GGK97E/metric/v/p/latitude",
    "ovms/ovms-mqtt-ggk97e/GGK97E/metric/v/p/odometer",
    "ovms/ovms-mqtt-ggk97e/GGK97E/metric/v/c/duration/full",
    "ovms/ovms-mqtt-ggk97e/GGK97E/metric/xvu/c/eff/calc",
    "ovms/ovms-mqtt-ggk97e/GGK97E/metric/v/b/p/temp/avg",
    "ovms/ovms-mqtt-ggk97e/GGK97E/metric/xvu/b/soc/abs",
    "ovms/ovms-mqtt-ggk97e/GGK97E/metric/xvu/e/hv/chgmode",
    "ovms/ovms-mqtt-ggk97e/GGK97E/metric/v/b/range/est",
    "ovms/ovms-mqtt-ggk97e/GGK97E/metric/v/p/longitude",
    "ovms/ovms-mqtt-ggk97e/GGK97E/metric/xvu/b/soh/vw",
    "ovms/ovms-mqtt-ggk97e/GGK97E/notify/alert/charge.stopped",
    "ovms/ovms-mqtt-ggk97e/GGK97E/metric/v/c/limit/soc",
    "ovms/ovms-mqtt-ggk97e/GGK97E/metric/v/b/soc",
    "ovms/ovms-mqtt-ggk97e/GGK97E/metric/v/p/gpssq",
    "ovms/ovms-mqtt-ggk97e/GGK97E/metric/v/b/12v/voltage",
    "ovms/ovms-mqtt-ggk97e/GGK97E/client/+/active",
    "ovms/ovms-mqtt-ggk97e/GGK97E/client/+/command/+",
]

# Topic patterns for discovery
METRIC_TOPIC_PATTERN = "{prefix}/{vehicle_name}/{vin}/metric/#"
NOTIFY_TOPIC_PATTERN = "{prefix}/{vehicle_name}/{vin}/notify/#"
CLIENT_TOPIC_PATTERN = "{prefix}/{vehicle_name}/{vin}/client/+/active"
COMMAND_TOPIC_PATTERN = "{prefix}/{vehicle_name}/{vin}/client/+/command/+"

# For dynamic topic discovery
TOPIC_DISCOVERY_PATTERNS = [
    METRIC_TOPIC_PATTERN,
    NOTIFY_TOPIC_PATTERN,
    CLIENT_TOPIC_PATTERN,
    COMMAND_TOPIC_PATTERN,
]
