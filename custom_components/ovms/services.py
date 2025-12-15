"""Services for OVMS integration."""

import logging
import uuid
from typing import Dict, Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_VEHICLE_ID, DEFAULT_COMMAND_TIMEOUT, DOMAIN, LOGGER_NAME
from .utils import get_merged_config

_LOGGER = logging.getLogger(LOGGER_NAME)

# Error message patterns that indicate firmware doesn't support a command
FIRMWARE_UNSUPPORTED_PATTERNS = [
    "Unrecognised command",
    "unrecognised command",
    "Unknown command",
    "unknown command",
    "Invalid command",
    "invalid command",
]

# Minimum firmware versions for edge-only features
EDGE_FIRMWARE_FEATURES = {
    "climate_schedule": "climatecontrol schedule commands require OVMS edge firmware (not in 3.3.005)",
    "tpms_map": "tpms map commands require OVMS edge firmware (not in 3.3.005)",
}


def _check_firmware_error(result: Dict[str, Any], feature_name: str) -> None:
    """Check if a command result indicates firmware doesn't support the command.

    Args:
        result: The result dictionary from async_send_command
        feature_name: The feature name for error messages (e.g., 'climate_schedule')

    Raises:
        HomeAssistantError: If the firmware doesn't support the command
    """
    if not result:
        return

    # Check for error responses
    response = result.get("response", "")
    if isinstance(response, str):
        for pattern in FIRMWARE_UNSUPPORTED_PATTERNS:
            if pattern in response:
                hint = EDGE_FIRMWARE_FEATURES.get(feature_name, "")
                error_msg = f"Command not supported by OVMS firmware: {response}"
                if hint:
                    error_msg += f". {hint}"
                raise HomeAssistantError(error_msg)


# Service name constants
SERVICE_SEND_COMMAND = "send_command"
SERVICE_SET_FEATURE = "set_feature"
SERVICE_CONTROL_CLIMATE = "control_climate"
SERVICE_CONTROL_CHARGING = "control_charging"
SERVICE_HOMELINK = "homelink"
SERVICE_CLIMATE_SCHEDULE = "climate_schedule"
SERVICE_TPMS_MAP = "tpms_map"
SERVICE_AUX_MONITOR = "aux_monitor"
SERVICE_REFRESH_METRICS = "refresh_metrics"

# Schema for the send_command service
SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required("vehicle_id"): cv.string,
        vol.Required("command"): cv.string,
        vol.Optional("parameters"): cv.string,
        vol.Optional("command_id"): cv.string,
        vol.Optional("timeout"): vol.Coerce(int),
    }
)

# Schema for the set_feature service
SET_FEATURE_SCHEMA = vol.Schema(
    {
        vol.Required("vehicle_id"): cv.string,
        vol.Required("feature"): cv.string,
        vol.Required("value"): cv.string,
    }
)

# Schema for the control_climate service
CONTROL_CLIMATE_SCHEMA = vol.Schema(
    {
        vol.Required("vehicle_id"): cv.string,
        vol.Optional("temperature"): vol.Coerce(float),
        vol.Optional("hvac_mode"): vol.In(["on", "off", "heat", "cool", "auto"]),
        vol.Optional("duration"): vol.Coerce(int),
    }
)

# Schema for the control_charging service
CONTROL_CHARGING_SCHEMA = vol.Schema(
    {
        vol.Required("vehicle_id"): cv.string,
        vol.Required("action"): vol.In(["start", "stop", "status"]),
        vol.Optional("mode"): vol.In(["standard", "storage", "range", "performance"]),
        vol.Optional("limit"): vol.Coerce(int),
    }
)

# Schema for the homelink service
HOMELINK_SCHEMA = vol.Schema(
    {
        vol.Required("vehicle_id"): cv.string,
        vol.Required("button"): vol.All(
            # Ensure it can handle both string and integer inputs
            vol.Coerce(int),
            vol.In([1, 2, 3]),
        ),
    }
)

# Schema for the climate_schedule service
CLIMATE_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("vehicle_id"): cv.string,
        vol.Required("action"): vol.In(
            ["set", "list", "clear", "copy", "enable", "disable", "status"]
        ),
        vol.Optional("day"): vol.In(
            ["mon", "tue", "wed", "thu", "fri", "sat", "sun", "all"]
        ),
        vol.Optional("times"): cv.string,
        vol.Optional("target_days"): cv.string,
    }
)

# Schema for the tpms_map service
TPMS_MAP_SCHEMA = vol.Schema(
    {
        vol.Required("vehicle_id"): cv.string,
        vol.Required("action"): vol.In(["status", "get", "set", "reset"]),
        vol.Optional("mapping"): cv.string,
    }
)

# Schema for the aux_monitor service
AUX_MONITOR_SCHEMA = vol.Schema(
    {
        vol.Required("vehicle_id"): cv.string,
        vol.Required("action"): vol.In(["status", "enable", "disable"]),
        vol.Optional("low_threshold"): vol.Coerce(float),
        vol.Optional("charging_threshold"): vol.Coerce(float),
    }
)

# Schema for the refresh_metrics service
REFRESH_METRICS_SCHEMA = vol.Schema(
    {
        vol.Required("vehicle_id"): cv.string,
        vol.Optional("pattern", default="*"): cv.string,
    }
)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up OVMS services."""

    def find_mqtt_client(vehicle_id: str):
        """Find the MQTT client for a vehicle ID synchronously."""
        for entry_id, data in hass.data[DOMAIN].items():
            if isinstance(data, dict) and "mqtt_client" in data:
                entry = hass.config_entries.async_get_entry(entry_id)
                if entry:
                    # Merge entry.data with entry.options, giving priority to options
                    config = get_merged_config(entry)
                    if config.get(CONF_VEHICLE_ID) == vehicle_id:
                        return data["mqtt_client"]
        return None

    def get_mqtt_client_or_raise(vehicle_id: str):
        """Get MQTT client for vehicle or raise HomeAssistantError."""
        mqtt_client = find_mqtt_client(vehicle_id)
        if not mqtt_client:
            raise HomeAssistantError(
                f"No OVMS integration found for vehicle_id: {vehicle_id}"
            )
        return mqtt_client

    async def async_send_command(call: ServiceCall) -> Dict[str, Any]:
        """Send a command to the OVMS module."""
        vehicle_id = call.data.get("vehicle_id")
        command = call.data.get("command")
        parameters = call.data.get("parameters", "")
        command_id = call.data.get("command_id", str(uuid.uuid4())[:8])
        timeout = call.data.get("timeout", 10)

        _LOGGER.debug(
            "Service call send_command for vehicle %s: %s %s",
            vehicle_id,
            command,
            parameters,
        )

        mqtt_client = get_mqtt_client_or_raise(vehicle_id)

        try:
            # Send the command and get the result
            result = await mqtt_client.async_send_command(
                command=command,
                parameters=parameters,
                command_id=command_id,
                timeout=timeout,
            )

            # Return the result as service data
            return result

        except Exception as ex:
            _LOGGER.exception("Error in send_command service: %s", ex)
            raise HomeAssistantError(f"Failed to send command: {ex}") from ex

    async def async_set_feature(call: ServiceCall) -> Dict[str, Any]:
        """Set a feature on the OVMS module."""
        vehicle_id = call.data.get("vehicle_id")
        feature = call.data.get("feature")
        value = call.data.get("value")

        _LOGGER.debug(
            "Service call set_feature for vehicle %s: %s=%s", vehicle_id, feature, value
        )

        mqtt_client = get_mqtt_client_or_raise(vehicle_id)

        try:
            # Format the command
            command = "config set"
            parameters = f"{feature} {value}"

            # Send the command and get the result
            result = await mqtt_client.async_send_command(
                command=command, parameters=parameters
            )

            return result

        except Exception as ex:
            _LOGGER.exception("Error in set_feature service: %s", ex)
            raise HomeAssistantError(f"Failed to set feature: {ex}") from ex

    async def async_control_climate(call: ServiceCall) -> Dict[str, Any]:
        """Control the vehicle's climate system."""
        vehicle_id = call.data.get("vehicle_id")
        temperature = call.data.get("temperature")
        hvac_mode = call.data.get("hvac_mode")
        duration = call.data.get("duration")

        _LOGGER.debug("Service call control_climate for vehicle %s", vehicle_id)

        mqtt_client = get_mqtt_client_or_raise(vehicle_id)

        try:
            # Build the climate command
            command = "climate"
            command_parts = []

            if hvac_mode == "off":
                command_parts.append("off")
            elif hvac_mode == "on":
                command_parts.append("on")
            else:
                if hvac_mode:
                    command_parts.append(hvac_mode)

                if temperature:
                    command_parts.append(f"temp {temperature}")

                if duration:
                    command_parts.append(f"duration {duration}")

            # Send the command and get the result
            result = await mqtt_client.async_send_command(
                command=command, parameters=" ".join(command_parts)
            )

            return result

        except Exception as ex:
            _LOGGER.exception("Error in control_climate service: %s", ex)
            raise HomeAssistantError(f"Failed to control climate: {ex}") from ex

    async def async_control_charging(call: ServiceCall) -> Dict[str, Any]:
        """Control the vehicle's charging system."""
        vehicle_id = call.data.get("vehicle_id")
        action = call.data.get("action")
        mode = call.data.get("mode")
        limit = call.data.get("limit")

        _LOGGER.debug(
            "Service call control_charging for vehicle %s: %s", vehicle_id, action
        )

        mqtt_client = get_mqtt_client_or_raise(vehicle_id)

        try:
            # Build the charge command
            command = "charge"
            command_parts = [action]

            if mode and action == "start":
                command_parts.append(f"mode {mode}")

            if limit is not None and action == "start":
                command_parts.append(f"limit {limit}")

            # Send the command and get the result
            result = await mqtt_client.async_send_command(
                command=command, parameters=" ".join(command_parts)
            )

            return result

        except Exception as ex:
            _LOGGER.exception("Error in control_charging service: %s", ex)
            raise HomeAssistantError(f"Failed to control charging: {ex}") from ex

    async def async_homelink(call: ServiceCall) -> Dict[str, Any]:
        """Activate a homelink button on the OVMS module."""
        vehicle_id = call.data.get("vehicle_id")
        button = call.data.get("button")

        _LOGGER.debug(
            "Service call homelink for vehicle %s: button %s", vehicle_id, button
        )

        mqtt_client = get_mqtt_client_or_raise(vehicle_id)

        try:
            # Format the command
            command = "homelink"
            parameters = str(button)

            # Send the command and get the result
            result = await mqtt_client.async_send_command(
                command=command, parameters=parameters
            )

            return result
        except Exception as ex:
            _LOGGER.exception("Error in homelink service: %s", ex)
            raise HomeAssistantError(f"Failed to activate homelink: {ex}") from ex

    async def async_climate_schedule(call: ServiceCall) -> Dict[str, Any]:
        """Manage scheduled precondition times for the vehicle's climate system.

        Supports multiple times per day with individual durations.
        See OVMS firmware changes.txt for command details.

        Note: This service requires OVMS edge firmware (not available in 3.3.005).
        """
        vehicle_id = call.data.get("vehicle_id")
        action = call.data.get("action")
        day = call.data.get("day")
        times = call.data.get("times")
        target_days = call.data.get("target_days")

        _LOGGER.debug(
            "Service call climate_schedule for vehicle %s: action=%s",
            vehicle_id,
            action,
        )

        mqtt_client = get_mqtt_client_or_raise(vehicle_id)

        try:
            # Build the climate schedule command
            command = "climatecontrol"

            if action == "set":
                if not day or not times:
                    raise HomeAssistantError(
                        "Both 'day' and 'times' are required for set action"
                    )
                parameters = f"schedule set {day} {times}"
            elif action == "list":
                parameters = "schedule list"
            elif action == "clear":
                if not day:
                    raise HomeAssistantError("'day' is required for clear action")
                parameters = f"schedule clear {day}"
            elif action == "copy":
                if not day or not target_days:
                    raise HomeAssistantError(
                        "Both 'day' and 'target_days' are required for copy action"
                    )
                parameters = f"schedule copy {day} {target_days}"
            elif action == "enable":
                parameters = "schedule enable"
            elif action == "disable":
                parameters = "schedule disable"
            elif action == "status":
                parameters = "schedule status"
            else:
                raise HomeAssistantError(f"Unknown action: {action}")

            result = await mqtt_client.async_send_command(
                command=command, parameters=parameters
            )

            # Check for firmware-related errors
            _check_firmware_error(result, "climate_schedule")

            return result

        except HomeAssistantError:
            raise
        except Exception as ex:
            _LOGGER.exception("Error in climate_schedule service: %s", ex)
            raise HomeAssistantError(f"Failed to manage climate schedule: {ex}") from ex

    async def async_tpms_map(call: ServiceCall) -> Dict[str, Any]:
        """Manage TPMS sensor-to-wheel mapping.

        Used for wheel rotation/swap scenarios.
        See OVMS firmware changes.txt for command details.

        Note: This service requires OVMS edge firmware (not available in 3.3.005).
        """
        vehicle_id = call.data.get("vehicle_id")
        action = call.data.get("action")
        mapping = call.data.get("mapping")

        _LOGGER.debug(
            "Service call tpms_map for vehicle %s: action=%s", vehicle_id, action
        )

        mqtt_client = get_mqtt_client_or_raise(vehicle_id)

        try:
            # Build the TPMS map command
            command = "tpms"

            if action == "status":
                parameters = "map status"
            elif action == "get":
                parameters = "map get"
            elif action == "set":
                if not mapping:
                    raise HomeAssistantError("'mapping' is required for set action")
                parameters = f"map set {mapping}"
            elif action == "reset":
                parameters = "map reset"
            else:
                raise HomeAssistantError(f"Unknown action: {action}")

            result = await mqtt_client.async_send_command(
                command=command, parameters=parameters
            )

            # Check for firmware-related errors
            _check_firmware_error(result, "tpms_map")

            return result

        except HomeAssistantError:
            raise
        except Exception as ex:
            _LOGGER.exception("Error in tpms_map service: %s", ex)
            raise HomeAssistantError(f"Failed to manage TPMS mapping: {ex}") from ex

    async def async_aux_monitor(call: ServiceCall) -> Dict[str, Any]:
        """Control the 12V auxiliary battery monitor.

        Used for automatic shutdown/reboot based on voltage levels.
        See OVMS firmware changes.txt for command details.
        """
        vehicle_id = call.data.get("vehicle_id")
        action = call.data.get("action")
        low_threshold = call.data.get("low_threshold")
        charging_threshold = call.data.get("charging_threshold")

        _LOGGER.debug(
            "Service call aux_monitor for vehicle %s: action=%s", vehicle_id, action
        )

        mqtt_client = get_mqtt_client_or_raise(vehicle_id)

        try:
            # Build the aux monitor command
            command = "vehicle"

            if action == "status":
                parameters = "aux monitor status"
            elif action == "enable":
                params = ["aux", "monitor", "enable"]
                if low_threshold is not None:
                    params.append(str(low_threshold))
                if charging_threshold is not None:
                    params.append(str(charging_threshold))
                parameters = " ".join(params)
            elif action == "disable":
                parameters = "aux monitor disable"
            else:
                raise HomeAssistantError(f"Unknown action: {action}")

            result = await mqtt_client.async_send_command(
                command=command, parameters=parameters
            )
            return result

        except HomeAssistantError:
            raise
        except Exception as ex:
            _LOGGER.exception("Error in aux_monitor service: %s", ex)
            raise HomeAssistantError(f"Failed to manage 12V aux monitor: {ex}") from ex

    async def async_refresh_metrics(call: ServiceCall) -> Dict[str, Any]:
        """Request metrics refresh from the OVMS module.

        Uses 'server v3 update all' command which works with all firmware.
        For edge firmware with pattern support, also sends on-demand request.
        """
        vehicle_id = call.data.get("vehicle_id")
        pattern = call.data.get("pattern", "*")

        _LOGGER.debug(
            "Service call refresh_metrics for vehicle %s: pattern=%s",
            vehicle_id,
            pattern,
        )

        mqtt_client = get_mqtt_client_or_raise(vehicle_id)

        # Always use 'server v3 update all' as primary method - works universally
        # The on-demand metric request only works with edge firmware and we can't
        # reliably detect firmware version from MQTT publish success alone
        try:
            result = await mqtt_client.async_send_command(
                command="server v3 update all",
                timeout=DEFAULT_COMMAND_TIMEOUT,
            )

            # Also send on-demand request for edge firmware (non-blocking bonus)
            # This provides pattern filtering for edge firmware users
            if pattern != "*":
                # Only send on-demand if user specified a pattern
                await mqtt_client.async_request_metrics(pattern)

            return {
                "success": True,
                "method": "server-command",
                "pattern": pattern,
                "message": "Requested all metrics via 'server v3 update all'",
                "response": result.get("response", ""),
            }
        except (OSError, TimeoutError, ValueError) as ex:
            _LOGGER.warning("Metric refresh via server command failed: %s", ex)
            raise HomeAssistantError(
                f"Failed to refresh metrics: {ex}. "
                "Ensure your OVMS module is online and connected."
            ) from ex

    # Register the services with response support for data-returning services
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        async_send_command,
        schema=SEND_COMMAND_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_FEATURE,
        async_set_feature,
        schema=SET_FEATURE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CONTROL_CLIMATE,
        async_control_climate,
        schema=CONTROL_CLIMATE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CONTROL_CHARGING,
        async_control_charging,
        schema=CONTROL_CHARGING_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_HOMELINK,
        async_homelink,
        schema=HOMELINK_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CLIMATE_SCHEDULE,
        async_climate_schedule,
        schema=CLIMATE_SCHEDULE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_TPMS_MAP,
        async_tpms_map,
        schema=TPMS_MAP_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_AUX_MONITOR,
        async_aux_monitor,
        schema=AUX_MONITOR_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_METRICS,
        async_refresh_metrics,
        schema=REFRESH_METRICS_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload OVMS services."""
    services = [
        SERVICE_SEND_COMMAND,
        SERVICE_SET_FEATURE,
        SERVICE_CONTROL_CLIMATE,
        SERVICE_CONTROL_CHARGING,
        SERVICE_HOMELINK,
        SERVICE_CLIMATE_SCHEDULE,
        SERVICE_TPMS_MAP,
        SERVICE_AUX_MONITOR,
        SERVICE_REFRESH_METRICS,
    ]
    for service in services:
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
