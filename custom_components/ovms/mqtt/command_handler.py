"""Command handler for OVMS integration."""

import asyncio
import logging
import time
import uuid
import json
from typing import Dict, Any, Optional

from homeassistant.core import HomeAssistant

from ..const import (
    LOGGER_NAME,
    CONF_QOS,
    CONF_VEHICLE_ID,
    DEFAULT_COMMAND_RATE_LIMIT,
    DEFAULT_COMMAND_RATE_PERIOD,
    COMMAND_TOPIC_TEMPLATE,
    RESPONSE_TOPIC_TEMPLATE,
)
from ..rate_limiter import CommandRateLimiter

_LOGGER = logging.getLogger(LOGGER_NAME)


class CommandHandler:
    """Handler for OVMS commands."""

    def __init__(self, hass: HomeAssistant, config: Dict[str, Any]):
        """Initialize the command handler."""
        self.hass = hass
        self.config = config
        self.pending_commands = {}
        self.command_limiter = CommandRateLimiter(
            max_calls=DEFAULT_COMMAND_RATE_LIMIT,
            period=DEFAULT_COMMAND_RATE_PERIOD,
        )
        self._cleanup_task = None
        self.structure_prefix = self._format_structure_prefix()

        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._async_cleanup_pending_commands())

    def _format_structure_prefix(self) -> str:
        """Format the topic structure prefix based on configuration."""
        try:
            structure = self.config.get(
                "topic_structure", "{prefix}/{mqtt_username}/{vehicle_id}"
            )
            prefix = self.config.get("topic_prefix")
            vehicle_id = self.config.get("vehicle_id")
            mqtt_username = self.config.get("mqtt_username", "")

            # Replace the variables in the structure
            structure_prefix = structure.format(
                prefix=prefix,
                vehicle_id=vehicle_id,
                mqtt_username=mqtt_username,
            )

            return structure_prefix
        except Exception as ex:
            _LOGGER.exception("Error formatting structure prefix: %s", ex)
            # Fallback to a simple default
            prefix = self.config.get("topic_prefix", "ovms")
            vehicle_id = self.config.get("vehicle_id", "")
            return f"{prefix}/{vehicle_id}"

    async def _async_cleanup_pending_commands(self) -> None:
        """Periodically clean up timed-out command requests."""
        while True:
            try:
                # Run every 60 seconds
                await asyncio.sleep(60)

                current_time = time.time()
                expired_commands = []

                for command_id, command_data in self.pending_commands.items():
                    # Check if command is older than 5 minutes
                    if current_time - command_data["timestamp"] > 300:
                        expired_commands.append(command_id)
                        _LOGGER.debug("Cleaning up expired command: %s", command_id)

                # Remove expired commands
                for command_id in expired_commands:
                    future = self.pending_commands[command_id]["future"]
                    if not future.done():
                        future.set_exception(
                            asyncio.TimeoutError("Command expired during cleanup")
                        )
                    if command_id in self.pending_commands:
                        del self.pending_commands[command_id]

                _LOGGER.debug("Cleaned up %d expired commands", len(expired_commands))

            except asyncio.CancelledError:
                # Handle task cancellation correctly
                _LOGGER.debug("Command cleanup task cancelled")
                break
            except Exception as ex:  # pylint: disable=broad-except
                _LOGGER.exception("Error in command cleanup task: %s", ex)
                # Wait a bit before retrying to avoid tight loop
                await asyncio.sleep(5)

    async def async_send_command(
        self,
        command: str,
        parameters: str = "",
        command_id: str = None,
        timeout: int = 10,
        vehicle_id: str = None,
    ) -> Dict[str, Any]:
        """Send a command to the OVMS module and wait for a response."""
        # Get the MQTT client
        mqtt_client = None
        for entry_id, data in self.hass.data["ovms"].items():
            if "mqtt_client" in data and hasattr(
                data["mqtt_client"], "connection_manager"
            ):
                current_vehicle_id = vehicle_id or self.config.get(CONF_VEHICLE_ID)
                if current_vehicle_id == self.config.get(CONF_VEHICLE_ID):
                    mqtt_client = data["mqtt_client"].connection_manager
                    break

        if not mqtt_client or not mqtt_client.connected:
            _LOGGER.error("Cannot send command, not connected to MQTT broker")
            return {"success": False, "error": "Not connected to MQTT broker"}

        # Check rate limiter
        if not self.command_limiter.can_call():
            time_to_next = self.command_limiter.time_to_next_call()
            _LOGGER.warning(
                "Command rate limit exceeded. Try again in %.1f seconds",
                time_to_next,
            )
            return {
                "success": False,
                "error": f"Rate limit exceeded. Try again in {time_to_next:.1f} seconds",
                "command": command,
                "parameters": parameters,
            }

        if command_id is None:
            command_id = uuid.uuid4().hex[:8]

        _LOGGER.debug(
            "Sending command: %s, parameters: %s, command_id: %s",
            command,
            parameters,
            command_id,
        )

        try:
            # Format the command topic
            command_topic = COMMAND_TOPIC_TEMPLATE.format(
                structure_prefix=self.structure_prefix, command_id=command_id
            )

            # Prepare the payload
            payload = command
            if parameters:
                payload = f"{command} {parameters}"

            # Create a future to wait for the response
            loop = asyncio.get_running_loop()
            future = loop.create_future()

            # Store the future for the response handler
            self.pending_commands[command_id] = {
                "future": future,
                "timestamp": time.time(),
                "command": command,
                "parameters": parameters,
            }

            # Send the command
            _LOGGER.debug("Publishing command to %s: %s", command_topic, payload)
            if not await mqtt_client.async_publish(
                command_topic, payload, qos=self.config.get(CONF_QOS)
            ):
                return {
                    "success": False,
                    "error": "Failed to publish command",
                    "command_id": command_id,
                    "command": command,
                    "parameters": parameters,
                }

            # Wait for the response with timeout
            _LOGGER.debug("Waiting for response for command_id: %s", command_id)
            response_payload = await asyncio.wait_for(future, timeout)

            # Enhanced logging for responses
            _LOGGER.debug("Received response: %s", response_payload)

            # Add INFO level logging with command context for easier tracking
            _LOGGER.info(
                "Command response for '%s %s' (ID: %s): %s",
                command,
                parameters,
                command_id,
                (
                    response_payload[:200] + "..."
                    if isinstance(response_payload, str) and len(response_payload) > 200
                    else response_payload
                ),
            )

            # Try to parse the response as JSON
            response_data = None
            try:
                response_data = json.loads(response_payload)
            except json.JSONDecodeError:
                # Not JSON, just use the raw payload
                response_data = response_payload

            # Return result
            return {
                "success": True,
                "command_id": command_id,
                "command": command,
                "parameters": parameters,
                "response": response_data,
            }

        except asyncio.TimeoutError:
            _LOGGER.warning(
                "Command '%s %s' (ID: %s) timed out after %d seconds. "
                "No response received from OVMS device. This could indicate: "
                "1) OVMS firmware doesn't support MQTT commands, "
                "2) OVMS device is not subscribed to command topics, "
                "3) OVMS device configuration issue. "
                "Try updating OVMS firmware or check OVMS MQTT configuration.",
                command,
                parameters,
                command_id,
                timeout,
            )
            # Clean up
            if command_id in self.pending_commands:
                del self.pending_commands[command_id]

            return {
                "success": False,
                "error": "Timeout waiting for response",
                "command_id": command_id,
                "command": command,
                "parameters": parameters,
            }

        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.exception("Error sending command: %s", ex)
            # Clean up
            if command_id in self.pending_commands:
                del self.pending_commands[command_id]

            return {
                "success": False,
                "error": str(ex),
                "command_id": command_id,
                "command": command,
                "parameters": parameters,
            }

    def process_response(self, topic: str, payload: str) -> None:
        """Process a response to a command."""
        try:
            # Extract command ID from response topic
            command_id = topic.split("/")[-1]

            _LOGGER.debug(
                "Processing command response for ID %s: %s", command_id, payload[:100]
            )

            # Look up pending command
            if command_id in self.pending_commands:
                future = self.pending_commands[command_id]["future"]
                if not future.done():
                    future.set_result(payload)
                    _LOGGER.debug("Successfully completed command %s", command_id)
                else:
                    _LOGGER.warning(
                        "Received response for already completed command %s", command_id
                    )

                # Clean up
                del self.pending_commands[command_id]
            else:
                # This can happen with QoS 1 message redelivery or stale messages
                _LOGGER.debug(
                    "Received response for command ID not in pending list: %s "
                    "(may be duplicate QoS 1 delivery or from another client)",
                    command_id,
                )

        except Exception as ex:
            _LOGGER.exception("Error processing command response: %s", ex)
