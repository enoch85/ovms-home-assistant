"""Utility functions for OVMS integration."""

from collections.abc import Awaitable, Callable
import logging
import hashlib
from typing import Any, Dict, Mapping, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_HOST,
    CONF_MQTT_USERNAME,
    CONF_PROTOCOL,
    CONF_USERNAME,
    CONF_VEHICLE_ID,
    CONF_VERIFY_SSL,
    DOMAIN,
    LOGGER_NAME,
    OVMS_DEVICE_MANUFACTURER,
    OVMS_DEVICE_MODEL,
    PIN_SECURE_PROTOCOLS,
)

_LOGGER = logging.getLogger(LOGGER_NAME)

CommandResult = dict[str, object]
CommandFunction = Callable[..., Awaitable[CommandResult]]


def get_merged_config(entry: ConfigEntry) -> Dict[str, Any]:
    """Get merged configuration from entry.data and entry.options.

    Options take precedence over data.

    Args:
        entry: The config entry containing data and options

    Returns:
        Merged configuration dictionary
    """
    config = {**entry.data}
    if entry.options:
        config.update(entry.options)
    return config


def get_ovms_topic_username(config: Mapping[str, Any]) -> str:
    """Return the OVMS topic-namespace username for a config."""
    mqtt_username = config.get(CONF_MQTT_USERNAME)
    if isinstance(mqtt_username, str) and mqtt_username.strip():
        return mqtt_username.strip()

    username = config.get(CONF_USERNAME)
    if isinstance(username, str) and username.strip():
        return username.strip()

    return ""


def _get_ovms_identity_base(config: Mapping[str, Any]) -> str:
    """Build the stable identity tuple for an OVMS config entry."""
    host = str(config.get(CONF_HOST, "")).strip()
    topic_username = get_ovms_topic_username(config)
    vehicle_id = str(config.get(CONF_VEHICLE_ID, "")).strip()
    return "|".join((host, topic_username, vehicle_id))


def generate_ovms_config_entry_unique_id(config: Mapping[str, Any]) -> str:
    """Generate a stable Home Assistant config-entry unique ID for OVMS."""
    identity_base = _get_ovms_identity_base(config)
    return f"ovms_{hashlib.sha256(identity_base.encode()).hexdigest()[:16]}"


def generate_ovms_client_id(config: Mapping[str, Any]) -> str:
    """Generate a stable MQTT client ID for OVMS.

    MQTT 3.1/3.1.1 client identifiers must remain short for compatibility, so the
    derived hash is capped at 12 hex characters: `ha_ovms_` + 12 = 20 chars.
    """
    identity_base = _get_ovms_identity_base(config)
    return f"ha_ovms_{hashlib.sha256(identity_base.encode()).hexdigest()[:12]}"


def uses_websocket_transport(config: Mapping[str, Any]) -> bool:
    """Return True when the configured MQTT transport uses websockets."""
    return config.get(CONF_PROTOCOL) in ("ws", "wss")


def uses_tls_transport(config: Mapping[str, Any]) -> bool:
    """Return True when the configured MQTT transport uses TLS."""
    return config.get(CONF_PROTOCOL) in ("mqtts", "wss")


def get_entry_command_function(
    hass: HomeAssistant, entry: ConfigEntry
) -> CommandFunction:
    """Get the shared OVMS command function for a config entry."""
    return hass.data[DOMAIN][entry.entry_id]["mqtt_client"].async_send_command


def get_namespaced_ovms_unique_id(
    unique_id: str, config_entry_id: Optional[str]
) -> str:
    """Return an OVMS unique ID scoped to a config entry.

    Home Assistant allows the config entry ID as a last-resort unique identifier.
    We use it as a namespace so multiple OVMS entries can coexist even when they
    expose the same vehicle_id and metric paths.
    """
    if not config_entry_id or not unique_id:
        return unique_id

    scoped_prefix = f"ovms_{config_entry_id}_"
    if unique_id.startswith(scoped_prefix):
        return unique_id

    if unique_id.startswith("ovms_"):
        return f"{scoped_prefix}{unique_id[5:]}"

    return f"{scoped_prefix}{unique_id}"


def get_ovms_device_identifier(
    client_id: Optional[str], vehicle_id: Optional[str]
) -> str:
    """Return the stable device registry identifier for an OVMS vehicle."""
    if client_id:
        return str(client_id)

    if vehicle_id:
        return str(vehicle_id).lower()

    return "unknown"


def get_ovms_device_name(vehicle_id: Optional[str]) -> str:
    """Return the Home Assistant device name for an OVMS vehicle.

    The integration name ("OVMS") is already shown in the HA UI breadcrumb
    and integration card, so the device name uses only the vehicle identifier
    to avoid redundant "OVMS ▸ OVMS - …" display.
    """
    return vehicle_id or "unknown"


def get_ovms_device_info(
    client_id: Optional[str],
    vehicle_id: Optional[str],
    sw_version: Optional[str] = None,
) -> Dict[str, Any]:
    """Build consistent Home Assistant device info for an OVMS vehicle."""
    device_info: Dict[str, Any] = {
        "identifiers": {(DOMAIN, get_ovms_device_identifier(client_id, vehicle_id))},
        "name": get_ovms_device_name(vehicle_id),
        "manufacturer": OVMS_DEVICE_MANUFACTURER,
        "model": OVMS_DEVICE_MODEL,
    }

    if sw_version is not None:
        device_info["sw_version"] = sw_version

    return device_info


def is_secure_pin_connection(config: Dict[str, Any]) -> bool:
    """Return True when PINs may be sent over the configured MQTT transport."""
    protocol = config.get(CONF_PROTOCOL)
    verify_ssl = config.get(CONF_VERIFY_SSL, False)
    return protocol in PIN_SECURE_PROTOCOLS and bool(verify_ssl)


def normalize_lock_pin(pin: Any) -> Optional[str]:
    """Normalize a configured or user-supplied lock PIN."""
    if pin is None:
        return None

    normalized = str(pin).strip()
    return normalized or None


def lock_pin_contains_whitespace(pin: str | None) -> bool:
    """Return True when a lock PIN contains unsupported whitespace."""
    if pin is None:
        return False

    return any(character.isspace() for character in pin)


def sanitize_topic_structure(value: Any) -> Optional[str]:
    """Strip leading/trailing whitespace from a topic structure string.

    Returns the stripped value, or None if the input is not a non-empty string.
    Guards against config entries saved with accidental whitespace
    (observed in issue #199).
    """
    if not isinstance(value, str):
        return None

    stripped = value.strip()
    return stripped if stripped else None


def safe_float(value: Any) -> Optional[float]:
    """Safely convert a value to float."""
    if value is None:
        return None

    try:
        return float(value)
    except (ValueError, TypeError):
        return None
