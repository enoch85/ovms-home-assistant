"""Services for OVMS integration."""
import logging
import uuid
from typing import Dict, Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_VEHICLE_ID,
    DOMAIN,
    LOGGER_NAME
)

_LOGGER = logging.getLogger(LOGGER_NAME)

# Service name constants
SERVICE_SEND_COMMAND = "send_command"
SERVICE_SET_FEATURE = "set_feature"
SERVICE_CONTROL_CLIMATE = "control_climate"
SERVICE_CONTROL_CHARGING = "control_charging"

# Schema for the send_command service
SEND_COMMAND_SCHEMA = vol.Schema({
    vol.Required("vehicle_id"): cv.string,
    vol.Required("command"): cv.string,
    vol.Optional("parameters"): cv.string,
    vol.Optional("command_id"): cv.string,
    vol.Optional("timeout"): vol.Coerce(int),
})

# Schema for the set_feature service
SET_FEATURE_SCHEMA = vol.Schema({
    vol.Required("vehicle_id"): cv.string,
    vol.Required("feature"): cv.string,
    vol.Required("value"): cv.string,
})

# Schema for the control_climate service
CONTROL_CLIMATE_SCHEMA = vol.Schema({
    vol.Required("vehicle_id"): cv.string,
    vol.Optional("temperature"): vol.Coerce(float),
    vol.Optional("hvac_mode"): vol.In(["off", "heat", "cool", "auto"]),
    vol.Optional("duration"): vol.Coerce(int),
})

# Schema for the control_charging service
CONTROL_CHARGING_SCHEMA = vol.Schema({
    vol.Required("vehicle_id"): cv.string,
    vol.Required("action"): vol.In(["start", "stop", "status"]),
    vol.Optional("mode"): vol.In(["standard", "storage", "range", "performance"]),
    vol.Optional("limit"): vol.Coerce(int),
})


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up OVMS services."""

    @callback
    def find_mqtt_client(vehicle_id: str):
        """Find the MQTT client for a vehicle ID synchronously."""
        for entry_id, data in hass.data[DOMAIN].items():
            if isinstance(data, dict) and "mqtt_client" in data:
                entry = hass.config_entries.async_get_entry(entry_id)
                if entry and entry.data.get(CONF_VEHICLE_ID) == vehicle_id:
                    return data["mqtt_client"]

        return None

    async def async_send_command(call: ServiceCall) -> Dict[str, Any]:
        """Send a command to the OVMS module."""
        vehicle_id = call.data.get("vehicle_id")
        command = call.data.get("command")
        parameters = call.data.get("parameters", "")
        command_id = call.data.get("command_id", str(uuid.uuid4())[:8])
        timeout = call.data.get("timeout", 10)

        _LOGGER.debug("Service call send_command for vehicle %s: %s %s",
                     vehicle_id, command, parameters)

        # Find client synchronously first
        mqtt_client = find_mqtt_client(vehicle_id)
        if not mqtt_client:
            raise HomeAssistantError(f"No OVMS integration found for vehicle_id: {vehicle_id}")

        try:
            # Send the command and get the result
            result = await mqtt_client.async_send_command(
                command=command,
                parameters=parameters,
                command_id=command_id,
                timeout=timeout
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

        _LOGGER.debug("Service call set_feature for vehicle %s: %s=%s",
                     vehicle_id, feature, value)

        # Find client synchronously first
        mqtt_client = find_mqtt_client(vehicle_id)
        if not mqtt_client:
            raise HomeAssistantError(f"No OVMS integration found for vehicle_id: {vehicle_id}")

        try:
            # Format the command
            command = "config set"
            parameters = f"{feature} {value}"

            # Send the command and get the result
            result = await mqtt_client.async_send_command(
                command=command,
                parameters=parameters
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

        # Find client synchronously first
        mqtt_client = find_mqtt_client(vehicle_id)
        if not mqtt_client:
            raise HomeAssistantError(f"No OVMS integration found for vehicle_id: {vehicle_id}")

        try:
            # Build the climate command
            command = "climate"
            command_parts = []

            if hvac_mode == "off":
                command_parts.append("off")
            else:
                if hvac_mode:
                    command_parts.append(hvac_mode)

                if temperature:
                    command_parts.append(f"temp {temperature}")

                if duration:
                    command_parts.append(f"duration {duration}")

            # Send the command and get the result
            result = await mqtt_client.async_send_command(
                command=command,
                parameters=" ".join(command_parts)
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

        _LOGGER.debug("Service call control_charging for vehicle %s: %s",
                     vehicle_id, action)

        # Find client synchronously first
        mqtt_client = find_mqtt_client(vehicle_id)
        if not mqtt_client:
            raise HomeAssistantError(f"No OVMS integration found for vehicle_id: {vehicle_id}")

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
                command=command,
                parameters=" ".join(command_parts)
            )

            return result

        except Exception as ex:
            _LOGGER.exception("Error in control_charging service: %s", ex)
            raise HomeAssistantError(f"Failed to control charging: {ex}") from ex

    # Register the services
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        async_send_command,
        schema=SEND_COMMAND_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_FEATURE,
        async_set_feature,
        schema=SET_FEATURE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CONTROL_CLIMATE,
        async_control_climate,
        schema=CONTROL_CLIMATE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CONTROL_CHARGING,
        async_control_charging,
        schema=CONTROL_CHARGING_SCHEMA,
    )


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload OVMS services."""
    services = [
        SERVICE_SEND_COMMAND,
        SERVICE_SET_FEATURE,
        SERVICE_CONTROL_CLIMATE,
        SERVICE_CONTROL_CHARGING,
    ]

    for service in services:
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
