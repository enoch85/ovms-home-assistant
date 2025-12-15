"""Topic discovery utilities for OVMS config flow."""

import asyncio
import logging
import re
import socket
import ssl
import time
import traceback
import uuid
from typing import Dict, Any, Optional, Set

import paho.mqtt.client as mqtt  # pylint: disable=import-error

from homeassistant.const import (  # pylint: disable=import-error
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    CONF_PROTOCOL,
)
from homeassistant.core import HomeAssistant  # pylint: disable=import-error

from ..const import (
    CONF_MQTT_USERNAME,
    CONF_TOPIC_PREFIX,
    CONF_TOPIC_STRUCTURE,
    CONF_VEHICLE_ID,
    CONF_QOS,
    CONF_VERIFY_SSL,
    DEFAULT_TOPIC_PREFIX,
    DEFAULT_TOPIC_STRUCTURE,
    DEFAULT_VERIFY_SSL,
    DISCOVERY_TOPIC,
    # Import outside toplevel fixed by importing here
    TOPIC_TEMPLATE as CONST_TOPIC_TEMPLATE,
    COMMAND_TOPIC_TEMPLATE as CONST_COMMAND_TOPIC_TEMPLATE,
    RESPONSE_TOPIC_TEMPLATE as CONST_RESPONSE_TOPIC_TEMPLATE,
    METRIC_REQUEST_TOPIC_TEMPLATE,
    ACTIVE_DISCOVERY_TIMEOUT,
    LEGACY_DISCOVERY_TIMEOUT,
    MINIMUM_DISCOVERY_PERCENT,
    GOOD_DISCOVERY_PERCENT,
    GENERIC_VEHICLE_TYPE,
    GENERIC_VEHICLE_NAME,
    LOGGER_NAME,
    ERROR_CANNOT_CONNECT,
    ERROR_TIMEOUT,
    ERROR_UNKNOWN,
)
from ..metrics.vehicles import VEHICLE_TYPE_PREFIXES, VEHICLE_TYPE_NAMES

_LOGGER = logging.getLogger(LOGGER_NAME)


def detect_vehicle_type(topics: Set[str]) -> tuple[str, str]:
    """Detect vehicle type from discovered topics.

    Looks for vehicle-specific metric prefixes (xvu., xse., xmg., xnl., xrt.)
    in the topic paths to determine the vehicle type.

    Args:
        topics: Set of discovered MQTT topics

    Returns:
        Tuple of (vehicle_type_id, vehicle_type_name)
        e.g., ("vw_eup", "VW e-UP!") or ("generic", "Generic OVMS")
    """
    for topic in topics:
        # Extract metric path from topic (last part after /metric/)
        if "/metric/" in topic:
            metric_path = topic.split("/metric/")[-1]
            # Check for vehicle-specific prefixes
            for prefix, vehicle_type in VEHICLE_TYPE_PREFIXES.items():
                if metric_path.startswith(prefix):
                    vehicle_name = VEHICLE_TYPE_NAMES.get(vehicle_type, vehicle_type)
                    _LOGGER.debug(
                        "Detected vehicle type '%s' (%s) from topic: %s",
                        vehicle_type,
                        vehicle_name,
                        topic,
                    )
                    return vehicle_type, vehicle_name

    return GENERIC_VEHICLE_TYPE, GENERIC_VEHICLE_NAME


def get_expected_metric_count(vehicle_type: str) -> int:
    """Get the expected number of metrics for a vehicle type.

    Calculates expected metrics by counting defined metrics from the metrics module.
    This provides a dynamic count based on actual metric definitions.

    Args:
        vehicle_type: Vehicle type identifier (e.g., "vw_eup", "generic")

    Returns:
        Expected number of metrics for this vehicle type
    """
    # Import here to avoid circular imports
    # pylint: disable=import-outside-toplevel
    from ..metrics import METRIC_DEFINITIONS

    # Common categories that apply to all vehicles
    common_categories = [
        "battery",
        "charging",
        "climate",
        "door",
        "location",
        "motor",
        "trip",
        "device",
        "diagnostic",
        "power",
        "network",
        "system",
        "tire",
    ]

    # Count common metrics
    common_count = sum(
        1 for v in METRIC_DEFINITIONS.values() if v.get("category") in common_categories
    )

    # Add vehicle-specific metrics if applicable
    if vehicle_type != "generic":
        vehicle_count = sum(
            1 for v in METRIC_DEFINITIONS.values() if v.get("category") == vehicle_type
        )
        total = common_count + vehicle_count
        _LOGGER.debug(
            "Expected metrics for %s: %d common + %d vehicle-specific = %d total",
            vehicle_type,
            common_count,
            vehicle_count,
            total,
        )
        return total

    _LOGGER.debug("Expected metrics for generic vehicle: %d common", common_count)
    return common_count


def calculate_discovery_percentage(
    metric_count: int, expected_count: int
) -> tuple[int, str]:
    """Calculate discovery percentage and quality indicator.

    Args:
        metric_count: Number of metrics actually discovered
        expected_count: Expected number of metrics for this vehicle type

    Returns:
        Tuple of (percentage, quality_indicator)
        Quality indicator is emoji: ✅ (>=70%), ⚠️ (>=30%), ❌ (<30%)
    """
    if expected_count <= 0:
        return 0, "❌"

    percentage = min(100, int((metric_count / expected_count) * 100))

    if percentage >= 70:
        quality = "✅"
    elif percentage >= 30:
        quality = "⚠️"
    else:
        quality = "❌"

    return percentage, quality


def format_structure_prefix(config):
    """Format the topic structure prefix based on configuration."""
    try:
        structure = config.get(CONF_TOPIC_STRUCTURE, DEFAULT_TOPIC_STRUCTURE)
        prefix = config.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
        vehicle_id = config.get(CONF_VEHICLE_ID, "")
        mqtt_username = config.get(CONF_MQTT_USERNAME, "")

        # Replace the variables in the structure
        structure_prefix = structure.format(
            prefix=prefix, vehicle_id=vehicle_id, mqtt_username=mqtt_username
        )

        _LOGGER.debug("Formatted structure prefix: %s", structure_prefix)
        return structure_prefix
    except Exception as ex:
        _LOGGER.exception("Error formatting structure prefix: %s", ex)
        # Fallback to a simple default
        prefix = config.get(CONF_TOPIC_PREFIX, "ovms")
        vehicle_id = config.get(CONF_VEHICLE_ID, "")
        return f"{prefix}/{vehicle_id}"


def format_metric_request_topic(config, client_id: str) -> str:
    """Format the metric request topic for on-demand metric requests.

    This topic is used with OVMS edge firmware to request all metrics
    immediately rather than waiting for passive discovery.

    Args:
        config: Configuration dictionary with topic structure settings
        client_id: The MQTT client ID making the request

    Returns:
        Formatted metric request topic string
    """
    structure_prefix = format_structure_prefix(config)
    return METRIC_REQUEST_TOPIC_TEMPLATE.format(
        structure_prefix=structure_prefix,
        client_id=client_id,
    )


def request_all_metrics(mqttc, config, client_id: str, qos: int = 1) -> bool:
    """Publish a request for all metrics to the OVMS module.

    This uses the on-demand metric request feature in OVMS edge firmware.
    Publishing "*" to the metric request topic causes OVMS to immediately
    publish all valid metrics to their normal topics.

    Args:
        mqttc: The MQTT client instance
        config: Configuration dictionary
        client_id: The MQTT client ID
        qos: Quality of Service level (default: 1)

    Returns:
        True if the publish was successful, False otherwise
    """
    try:
        metric_request_topic = format_metric_request_topic(config, client_id)
        _LOGGER.debug(
            "Requesting all metrics via topic: %s with payload '*'",
            metric_request_topic,
        )
        result = mqttc.publish(metric_request_topic, "*", qos=qos)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            _LOGGER.info(
                "Successfully published metric request to %s", metric_request_topic
            )
            return True
        _LOGGER.warning("Failed to publish metric request, rc=%s", result.rc)
        return False
    except Exception as ex:
        _LOGGER.warning("Error requesting metrics: %s", ex)
        return False


def extract_vehicle_ids(topics, config):
    """Extract potential vehicle IDs from discovered topics."""
    _LOGGER.debug("Extracting potential vehicle IDs from %d topics", len(topics))
    potential_ids = set()
    discovered_username = None

    # Get the configured topic structure and components
    structure = config.get(CONF_TOPIC_STRUCTURE, DEFAULT_TOPIC_STRUCTURE)
    prefix = config.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX) or DEFAULT_TOPIC_PREFIX
    mqtt_username = config.get(CONF_MQTT_USERNAME, "")

    # Phase 1: Try exact structure matching first
    if structure != "custom":
        # Convert structure to regex pattern, keeping vehicle_id as a capture group
        # Replace {prefix} and {mqtt_username} with their actual values
        # Keep {vehicle_id} as a capture group
        pattern_str = structure.replace("{prefix}", re.escape(prefix))
        if mqtt_username:
            pattern_str = pattern_str.replace(
                "{mqtt_username}", re.escape(mqtt_username)
            )
        else:
            # Handle case when username isn't provided but is in the structure
            pattern_str = pattern_str.replace("{mqtt_username}", "[^/]+")

        # Convert {vehicle_id} to a capture group
        pattern_str = pattern_str.replace("{vehicle_id}", "([^/]+)")
        # Add trailing slash and wildcard
        pattern_str = f"^{pattern_str}/.*"

        _LOGGER.debug("Using exact structure pattern: %s", pattern_str)
        exact_pattern = re.compile(pattern_str)

        # Check topics against exact pattern
        for topic in topics:
            match = exact_pattern.match(topic)
            if match and len(match.groups()) > 0:
                vehicle_id = match.group(1)
                if vehicle_id not in ["client", "rr"]:
                    _LOGGER.debug(
                        "Found potential vehicle ID '%s' from exact structure match in topic '%s'",
                        vehicle_id,
                        topic,
                    )
                    potential_ids.add(vehicle_id)

    # Phase 2: Only if no IDs found with exact structure, use the generic pattern approach
    if not potential_ids:
        _LOGGER.debug(
            "No vehicle IDs found with exact structure, trying generic pattern"
        )

        # General pattern to match various username formats for OVMS
        general_pattern = rf"^{re.escape(prefix)}/([^/]+)/([^/]+)/"
        _LOGGER.debug(
            "Using general pattern to extract vehicle IDs: %s", general_pattern
        )

        for topic in topics:
            match = re.match(general_pattern, topic)
            if match and len(match.groups()) > 1:
                username = match.group(1)
                vehicle_id = match.group(2)
                if vehicle_id not in ["client", "rr"]:
                    _LOGGER.debug(
                        "Found potential vehicle ID '%s' with username '%s' from topic '%s'",
                        vehicle_id,
                        username,
                        topic,
                    )
                    # Save the discovered username for future use
                    discovered_username = username
                    potential_ids.add(vehicle_id)

    # Update the MQTT username in config if discovered
    if discovered_username:
        current_username = config.get(CONF_MQTT_USERNAME, "")
        if current_username != discovered_username:
            _LOGGER.debug(
                "Updating MQTT username from '%s' to discovered '%s'",
                current_username,
                discovered_username,
            )
            config[CONF_MQTT_USERNAME] = discovered_username

    _LOGGER.debug(
        "Extracted %d potential vehicle IDs: %s", len(potential_ids), potential_ids
    )
    return potential_ids


# pylint: disable=too-many-locals,too-many-branches,too-many-statements,too-many-return-statements
async def discover_topics(hass: HomeAssistant, config):
    """Discover available OVMS topics on the broker."""
    topic_prefix = config.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
    log_prefix = f"Topic discovery for prefix {topic_prefix}"
    _LOGGER.debug("%s - Starting", log_prefix)

    # Initialize debug info for this test
    debug_info = {
        "topic_prefix": topic_prefix,
        "test_start_time": asyncio.get_event_loop().time(),
    }

    # Format the discovery topic
    discovery_topic = DISCOVERY_TOPIC.format(prefix=topic_prefix)
    _LOGGER.debug("%s - Using discovery topic: %s", log_prefix, discovery_topic)
    debug_info["discovery_topic"] = discovery_topic

    # Set up a test client
    client_id = f"ha_ovms_discovery_{uuid.uuid4().hex[:8]}"
    protocol = mqtt.MQTTv5 if hasattr(mqtt, "MQTTv5") else mqtt.MQTTv311

    _LOGGER.debug("%s - Creating client with ID: %s", log_prefix, client_id)
    mqttc = mqtt.Client(client_id=client_id, protocol=protocol)

    discovered_topics = set()
    connection_status = {"connected": False, "rc": None}

    # Define callbacks
    def on_connect(_, __, flags, rc, _properties=None):
        """Handle connection result."""
        connection_status["connected"] = rc == 0
        connection_status["rc"] = rc
        # Using time.time() instead of asyncio.get_event_loop().time()
        connection_status["timestamp"] = time.time()

        _LOGGER.debug(
            "%s - Connection callback: rc=%s, flags=%s", log_prefix, rc, flags
        )

        if rc == 0:
            _LOGGER.debug(
                "%s - Subscribing to discovery topic: %s", log_prefix, discovery_topic
            )
            mqttc.subscribe(discovery_topic, qos=config.get(CONF_QOS, 1))

    def on_message(_, __, msg):
        """Handle incoming messages."""
        _LOGGER.debug(
            "%s - Message received on topic: %s (payload len: %d)",
            log_prefix,
            msg.topic,
            len(msg.payload),
        )
        discovered_topics.add(msg.topic)

    def on_disconnect(_, __, rc, _properties=None):
        """Handle disconnection."""
        connection_status["connected"] = False
        connection_status["disconnect_rc"] = rc
        # Using time.time() instead of asyncio.get_event_loop().time()
        connection_status["disconnect_timestamp"] = time.time()
        _LOGGER.debug("%s - Disconnected with result code: %s", log_prefix, rc)

    def on_log(_, __, ___, buf):
        """Log MQTT client internal messages."""
        _LOGGER.debug("%s - MQTT Log: %s", log_prefix, buf)

    # Configure the client
    if hasattr(mqtt, "MQTTv5"):
        mqttc.on_connect = on_connect
    else:
        # For MQTT v3.1.1
        def on_connect_v311(client, userdata, flags, rc):
            on_connect(client, userdata, flags, rc, None)

        mqttc.on_connect = on_connect_v311

    mqttc.on_message = on_message
    mqttc.on_disconnect = on_disconnect
    mqttc.on_log = on_log

    if CONF_USERNAME in config and config[CONF_USERNAME]:
        _LOGGER.debug("%s - Setting username: %s", log_prefix, config[CONF_USERNAME])
        mqttc.username_pw_set(
            username=config[CONF_USERNAME],
            password=config[CONF_PASSWORD] if CONF_PASSWORD in config else None,
        )

    if config[CONF_PORT] == 8883:
        verify_ssl = config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
        try:
            # Use executor to avoid blocking the event loop
            context = await hass.async_add_executor_job(ssl.create_default_context)
            # Allow self-signed certificates if verification is disabled
            if not verify_ssl:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            mqttc.tls_set_context(context)
            debug_info["tls_enabled"] = True
            debug_info["tls_verify"] = verify_ssl
        except ssl.SSLError as ssl_err:
            _LOGGER.error("%s - SSL/TLS setup error: %s", log_prefix, ssl_err)
            debug_info["ssl_error"] = str(ssl_err)
            return {
                "success": False,
                "error_type": ERROR_CANNOT_CONNECT,
                "message": f"SSL/TLS Error: {ssl_err}",
            }

    # Set up connection timeout
    mqttc.connect_timeout = 5.0

    try:
        # Connect to the broker
        _LOGGER.debug("%s - Connecting to broker", log_prefix)
        await hass.async_add_executor_job(
            mqttc.connect,
            config[CONF_HOST],
            config[CONF_PORT],
            60,  # Keep alive timeout
        )

        # Start the loop in a separate thread
        mqttc.loop_start()

        # Wait for connection to establish
        connected = False
        for i in range(10):  # Try for up to 5 seconds
            if connection_status.get("connected"):
                connected = True
                break
            await asyncio.sleep(0.5)
            _LOGGER.debug("%s - Waiting for connection (%d/10)", log_prefix, i + 1)

        if not connected:
            mqttc.loop_stop()
            rc = connection_status.get("rc", "unknown")
            _LOGGER.error("%s - Connection failed, rc=%s", log_prefix, rc)
            return {
                "success": False,
                "error_type": ERROR_CANNOT_CONNECT,
                "message": f"Failed to connect to MQTT broker (rc={rc})",
            }

        # Hybrid discovery strategy:
        # 1. If retained messages already provided enough metrics, skip active/legacy
        # 2. Otherwise try active metric request (OVMS edge firmware) with short timeout
        # 3. If no/few topics found, fall back to legacy passive discovery

        # Helper to count only metric topics (excludes /client/ command/response topics)
        def count_metric_topics(topics):
            """Count topics that are actual metrics, not command/response echoes."""
            return sum(1 for t in topics if "/metric/" in t)

        # Track whether active discovery succeeded
        active_discovery_succeeded = False
        # Count only metric topics, not /client/ echoes (Issue 1 fix)
        metric_topics_before = count_metric_topics(discovered_topics)

        # Get expected metrics for percentage calculation
        # We detect vehicle type early to calculate thresholds
        vehicle_type_early, _ = detect_vehicle_type(discovered_topics)
        expected_count_early = get_expected_metric_count(vehicle_type_early)
        retained_percentage = (
            int((metric_topics_before / expected_count_early) * 100)
            if expected_count_early > 0
            else 0
        )

        # Check if retained messages already gave us enough metrics (percentage-based)
        # This happens when broker has retained messages from a running OVMS module
        if retained_percentage >= GOOD_DISCOVERY_PERCENT:
            _LOGGER.info(
                "%s - Already received %d metric topics (%d%%) from retained messages, "
                "skipping active discovery",
                log_prefix,
                metric_topics_before,
                retained_percentage,
            )
            active_discovery_succeeded = True
            debug_info["discovery_method"] = "retained"
            debug_info["retained_metric_topics"] = metric_topics_before
        else:
            # Phase 1: Try active metric request (OVMS edge firmware)
            _LOGGER.debug(
                "%s - Attempting active metric request (OVMS edge firmware)", log_prefix
            )
            try:
                if request_all_metrics(
                    mqttc, config, client_id, config.get(CONF_QOS, 1)
                ):
                    # Wait for active discovery timeout
                    _LOGGER.debug(
                        "%s - Waiting %d seconds for active discovery response",
                        log_prefix,
                        ACTIVE_DISCOVERY_TIMEOUT,
                    )
                    await asyncio.sleep(ACTIVE_DISCOVERY_TIMEOUT)

                    # Count only metric topics to avoid false success from echoed requests
                    metric_topics_after = count_metric_topics(discovered_topics)
                    new_metric_topics = metric_topics_after - metric_topics_before

                    if new_metric_topics > 0:
                        _LOGGER.info(
                            "%s - Active discovery succeeded: received %d new metric topics",
                            log_prefix,
                            new_metric_topics,
                        )
                        active_discovery_succeeded = True
                        debug_info["discovery_method"] = "active"
                        debug_info["active_discovery_topics"] = new_metric_topics
                    else:
                        _LOGGER.debug(
                            "%s - No metric topics from active request (got %d total topics, may be echoes), firmware may be older",
                            log_prefix,
                            len(discovered_topics) - metric_topics_before,
                        )
            except Exception as ex:  # pylint: disable=broad-except
                _LOGGER.debug("%s - Active metric request failed: %s", log_prefix, ex)

        # Phase 2: Legacy discovery (wait for passive messages or send stat command)
        if not active_discovery_succeeded:
            _LOGGER.debug("%s - Falling back to legacy passive discovery", log_prefix)
            debug_info["discovery_method"] = "legacy"

            # Calculate remaining wait time for legacy discovery
            # We already waited ACTIVE_DISCOVERY_TIMEOUT, so wait the difference
            remaining_wait = max(0, LEGACY_DISCOVERY_TIMEOUT - ACTIVE_DISCOVERY_TIMEOUT)
            _LOGGER.debug(
                "%s - Legacy discovery: waiting %d seconds (total %d seconds)",
                log_prefix,
                remaining_wait,
                LEGACY_DISCOVERY_TIMEOUT,
            )

            # Try to publish a message to stimulate response
            try:
                _LOGGER.debug(
                    "%s - Publishing test message to stimulate responses", log_prefix
                )
                command_id = uuid.uuid4().hex[:8]
                # Use a generic discovery command - this will be ignored if structure wrong
                # but might trigger responses from OVMS modules
                test_topic = f"{topic_prefix}/client/rr/command/{command_id}"
                test_payload = "stat"

                mqttc.publish(test_topic, test_payload, qos=config.get(CONF_QOS, 1))
                _LOGGER.debug(
                    "%s - Test message published to %s", log_prefix, test_topic
                )

                # Also try a more generic topic to catch any responding devices
                vehicle_id = config.get(CONF_VEHICLE_ID, "")
                if vehicle_id:
                    alt_test_topic = (
                        f"{topic_prefix}/+/{vehicle_id}/client/rr/command/{command_id}"
                    )
                    mqttc.publish(
                        alt_test_topic, test_payload, qos=config.get(CONF_QOS, 1)
                    )
                    _LOGGER.debug(
                        "%s - Also testing alternative topic: %s",
                        log_prefix,
                        alt_test_topic,
                    )
            except Exception as ex:  # pylint: disable=broad-except
                _LOGGER.warning(
                    "%s - Error publishing test message: %s", log_prefix, ex
                )

            # Wait the remaining time for legacy discovery
            if remaining_wait > 0:
                _LOGGER.debug(
                    "%s - Waiting %d seconds for passive discovery",
                    log_prefix,
                    remaining_wait,
                )
                await asyncio.sleep(remaining_wait)
                _LOGGER.debug(
                    "%s - Test message error details: %s",
                    log_prefix,
                    traceback.format_exc(),
                )

        # Clean up
        mqttc.loop_stop()
        try:
            mqttc.disconnect()
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.debug("%s - Error disconnecting: %s", log_prefix, ex)

        # Process discovery results
        topics_count = len(discovered_topics)
        metric_topics = [t for t in discovered_topics if "/metric/" in t]
        metric_count = len(metric_topics)

        # Detect vehicle type and calculate expected metrics
        vehicle_type, vehicle_name = detect_vehicle_type(discovered_topics)
        expected_count = get_expected_metric_count(vehicle_type)
        discovery_percentage, quality_indicator = calculate_discovery_percentage(
            metric_count, expected_count
        )

        debug_info["topics_count"] = topics_count
        debug_info["metric_count"] = metric_count
        debug_info["vehicle_type"] = vehicle_type
        debug_info["vehicle_name"] = vehicle_name
        debug_info["expected_count"] = expected_count
        debug_info["discovery_percentage"] = discovery_percentage
        debug_info["discovered_topics"] = (
            list(discovered_topics)
            if len(discovered_topics) < 50
            else list(discovered_topics)[:50]
        )

        _LOGGER.debug(
            "%s - Discovery complete. Found %d topics (%d metric topics). "
            "Vehicle: %s. Coverage: %d%% (%d/%d expected)",
            log_prefix,
            topics_count,
            metric_count,
            vehicle_name,
            discovery_percentage,
            metric_count,
            expected_count,
        )

        # Build result
        result = {
            "success": True,
            "discovered_topics": discovered_topics,
            "topic_count": topics_count,
            "metric_count": metric_count,
            "vehicle_type": vehicle_type,
            "vehicle_name": vehicle_name,
            "expected_count": expected_count,
            "discovery_percentage": discovery_percentage,
            "quality_indicator": quality_indicator,
            "debug_info": debug_info,
        }

        if discovery_percentage < MINIMUM_DISCOVERY_PERCENT:
            result["warning"] = "few_topics"
            _LOGGER.warning(
                "%s - Only %d metric topics found (%d%%, minimum recommended: %d%%). "
                "Check that your OVMS module is online and publishing metrics.",
                log_prefix,
                metric_count,
                discovery_percentage,
                MINIMUM_DISCOVERY_PERCENT,
            )

        return result

    except socket.timeout:
        _LOGGER.error("%s - Connection timeout", log_prefix)
        return {
            "success": False,
            "error_type": ERROR_TIMEOUT,
            "message": "Connection timeout during topic discovery",
        }
    # Fixed except clauses order: more specific exceptions first
    except ConnectionError as conn_ex:
        _LOGGER.error("%s - Connection error: %s", log_prefix, conn_ex)
        _LOGGER.debug(
            "%s - Connection error details: %s", log_prefix, traceback.format_exc()
        )
        return {
            "success": False,
            "error_type": ERROR_CANNOT_CONNECT,
            "message": f"Connection error during topic discovery: {conn_ex}",
        }
    except TimeoutError as timeout_ex:
        _LOGGER.error("%s - Timeout error: %s", log_prefix, timeout_ex)
        _LOGGER.debug(
            "%s - Timeout error details: %s", log_prefix, traceback.format_exc()
        )
        return {
            "success": False,
            "error_type": ERROR_TIMEOUT,
            "message": f"Timeout error during topic discovery: {timeout_ex}",
        }
    except socket.error as socket_err:
        _LOGGER.error("%s - Connection error: %s", log_prefix, socket_err)
        _LOGGER.debug(
            "%s - Connection error details: %s", log_prefix, traceback.format_exc()
        )
        return {
            "success": False,
            "error_type": ERROR_CANNOT_CONNECT,
            "message": f"Connection error during topic discovery: {socket_err}",
        }
    except Exception as ex:  # pylint: disable=broad-except
        _LOGGER.error("%s - MQTT error: %s", log_prefix, ex)
        _LOGGER.debug("%s - MQTT error details: %s", log_prefix, traceback.format_exc())
        return {
            "success": False,
            "error_type": ERROR_UNKNOWN,
            "message": f"Error during topic discovery: {ex}",
        }


# pylint: disable=too-many-locals,too-many-branches,too-many-statements,too-many-return-statements
async def test_topic_availability(hass: HomeAssistant, config):
    """Test if the OVMS topics are available for a specific vehicle."""
    vehicle_id = config[CONF_VEHICLE_ID]
    log_prefix = f"Topic availability test for vehicle {vehicle_id}"
    _LOGGER.debug("%s - Starting", log_prefix)

    # Format the structure prefix for this vehicle
    structure_prefix = format_structure_prefix(config)

    # Initialize debug info for this test
    debug_info = {
        "vehicle_id": vehicle_id,
        "structure_prefix": structure_prefix,
        "test_start_time": asyncio.get_event_loop().time(),
    }

    # Format the topic template
    topic = CONST_TOPIC_TEMPLATE.format(structure_prefix=structure_prefix)
    _LOGGER.debug("%s - Using subscription topic: %s", log_prefix, topic)
    debug_info["subscription_topic"] = topic

    # Format command and response topics for request-response test
    command_id = uuid.uuid4().hex[:8]
    command_topic = CONST_COMMAND_TOPIC_TEMPLATE.format(
        structure_prefix=structure_prefix, command_id=command_id
    )
    response_topic = CONST_RESPONSE_TOPIC_TEMPLATE.format(
        structure_prefix=structure_prefix, command_id=command_id
    )

    _LOGGER.debug("%s - Using command topic: %s", log_prefix, command_topic)
    _LOGGER.debug("%s - Using response topic: %s", log_prefix, response_topic)

    debug_info["command_topic"] = command_topic
    debug_info["response_topic"] = response_topic

    # Set up a test client
    client_id = f"ha_ovms_topic_test_{uuid.uuid4().hex[:8]}"
    protocol = mqtt.MQTTv5 if hasattr(mqtt, "MQTTv5") else mqtt.MQTTv311

    _LOGGER.debug("%s - Creating client with ID: %s", log_prefix, client_id)
    mqttc = mqtt.Client(client_id=client_id, protocol=protocol)

    messages_received = []
    topics_found = set()
    connection_status = {"connected": False, "rc": None}
    responses_received = []

    # Define callbacks
    def on_connect(_, __, flags, rc, _properties=None):
        """Handle connection result."""
        connection_status["connected"] = rc == 0
        connection_status["rc"] = rc
        # Using time.time() instead of asyncio.get_event_loop().time()
        connection_status["timestamp"] = time.time()

        _LOGGER.debug(
            "%s - Connection callback: rc=%s, flags=%s", log_prefix, rc, flags
        )

        if rc == 0:
            # Subscribe to general topics and response topic
            _LOGGER.debug("%s - Subscribing to general topic: %s", log_prefix, topic)
            mqttc.subscribe(topic, qos=config.get(CONF_QOS, 1))

            _LOGGER.debug(
                "%s - Subscribing to response topic: %s", log_prefix, response_topic
            )
            mqttc.subscribe(response_topic, qos=config.get(CONF_QOS, 1))

            # Also try a direct subscription to known topic patterns
            prefix = config.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
            if prefix:
                # Try with the actual username instead of placeholder
                mqtt_username = config.get(CONF_MQTT_USERNAME, "")
                if mqtt_username:
                    direct_topic = f"{prefix}/{mqtt_username}/{vehicle_id}/#"
                    _LOGGER.debug(
                        "%s - Also subscribing to direct topic: %s",
                        log_prefix,
                        direct_topic,
                    )
                    mqttc.subscribe(direct_topic, qos=config.get(CONF_QOS, 1))

                # Also try with the pattern matching any username
                alt_topic = f"{prefix}/+/{vehicle_id}/#"
                _LOGGER.debug(
                    "%s - Also subscribing to alternative topic: %s",
                    log_prefix,
                    alt_topic,
                )
                mqttc.subscribe(alt_topic, qos=config.get(CONF_QOS, 1))

    def on_message(_, __, msg):
        """Handle incoming messages."""
        _LOGGER.debug(
            "%s - Message received on topic: %s (payload len: %d)",
            log_prefix,
            msg.topic,
            len(msg.payload),
        )

        message_info = {
            "topic": msg.topic,
            "payload_length": len(msg.payload),
            # Using time.time() instead of asyncio.get_event_loop().time()
            "timestamp": time.time(),
        }

        # Try to decode payload for logging
        try:
            payload_str = msg.payload.decode("utf-8")
            message_info["payload"] = payload_str
            _LOGGER.debug("%s - Payload: %s", log_prefix, payload_str)
        except UnicodeDecodeError:
            message_info["payload"] = "<binary data>"
            _LOGGER.debug("%s - Payload: <binary data>", log_prefix)

        # Track all messages
        messages_received.append(message_info)
        topics_found.add(msg.topic)

        # Check if this is a response to our command
        if msg.topic == response_topic:
            _LOGGER.debug("%s - Response received for command!", log_prefix)
            responses_received.append(message_info)

    def on_disconnect(_, __, rc, _properties=None):
        """Handle disconnection."""
        connection_status["connected"] = False
        connection_status["disconnect_rc"] = rc
        # Using time.time() instead of asyncio.get_event_loop().time()
        connection_status["disconnect_timestamp"] = time.time()
        _LOGGER.debug("%s - Disconnected with result code: %s", log_prefix, rc)

    def on_log(_, __, ___, buf):
        """Log MQTT client internal messages."""
        _LOGGER.debug("%s - MQTT Log: %s", log_prefix, buf)

    # Configure the client
    if hasattr(mqtt, "MQTTv5"):
        mqttc.on_connect = on_connect
    else:
        # For MQTT v3.1.1
        def on_connect_v311(client, userdata, flags, rc):
            on_connect(client, userdata, flags, rc, None)

        mqttc.on_connect = on_connect_v311

    mqttc.on_message = on_message
    mqttc.on_disconnect = on_disconnect
    mqttc.on_log = on_log

    if CONF_USERNAME in config and config[CONF_USERNAME]:
        _LOGGER.debug("%s - Setting username: %s", log_prefix, config[CONF_USERNAME])
        mqttc.username_pw_set(
            username=config[CONF_USERNAME],
            password=config[CONF_PASSWORD] if CONF_PASSWORD in config else None,
        )

    # Configure TLS if needed
    if config[CONF_PROTOCOL] == "mqtts":
        _LOGGER.debug("%s - Enabling SSL/TLS for port 8883", log_prefix)
        verify_ssl = config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)

        try:
            # Use executor to avoid blocking the event loop
            context = await hass.async_add_executor_job(ssl.create_default_context)
            # Allow self-signed certificates if verification is disabled
            if not verify_ssl:
                _LOGGER.debug("%s - SSL certificate verification disabled", log_prefix)
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            mqttc.tls_set_context(context)
            debug_info["tls_enabled"] = True
            debug_info["tls_verify"] = verify_ssl
        except ssl.SSLError as ssl_err:
            _LOGGER.error("%s - SSL/TLS setup error: %s", log_prefix, ssl_err)
            debug_info["ssl_error"] = str(ssl_err)
            return {
                "success": False,
                "error_type": ERROR_CANNOT_CONNECT,
                "message": f"SSL/TLS Error: {ssl_err}",
                "details": f"SSL configuration failed: {ssl_err}",
                "debug_info": debug_info,
            }

    # Set up connection timeout
    mqttc.connect_timeout = 5.0

    try:
        # Connect to the broker
        _LOGGER.debug("%s - Connecting to broker", log_prefix)
        await hass.async_add_executor_job(
            mqttc.connect,
            config[CONF_HOST],
            config[CONF_PORT],
            60,  # Keep alive timeout
        )

        # Start the loop in a separate thread
        mqttc.loop_start()

        # Wait for connection to establish
        connected = False
        for i in range(10):  # Try for up to 5 seconds
            if connection_status.get("connected"):
                connected = True
                break
            await asyncio.sleep(0.5)
            _LOGGER.debug("%s - Waiting for connection (%d/10)", log_prefix, i + 1)

        if not connected:
            mqttc.loop_stop()
            rc = connection_status.get("rc", "unknown")
            _LOGGER.error("%s - Connection failed, rc=%s", log_prefix, rc)
            return {
                "success": False,
                "error_type": ERROR_CANNOT_CONNECT,
                "message": f"Failed to connect to MQTT broker (rc={rc})",
                "details": f"Could not connect to broker for topic testing. Result code: {rc}",
                "debug_info": debug_info,
            }

        # Wait for some initial messages
        _LOGGER.debug("%s - Waiting for initial messages", log_prefix)
        for i in range(5):  # Wait for up to 2.5 seconds
            if messages_received:
                break
            _LOGGER.debug("%s - No messages yet (%d/5)", log_prefix, i + 1)
            await asyncio.sleep(0.5)

        # Send a command to test request-response
        _LOGGER.debug("%s - Sending test command to: %s", log_prefix, command_topic)

        try:
            # Use 'stat' command which should work with OVMS
            mqttc.publish(command_topic, "stat", qos=config.get(CONF_QOS, 1))

            # Wait for a response
            _LOGGER.debug("%s - Waiting for command response", log_prefix)
            for i in range(10):  # Wait for up to 5 seconds
                if responses_received:
                    break
                _LOGGER.debug("%s - No response yet (%d/10)", log_prefix, i + 1)
                await asyncio.sleep(0.5)

            if responses_received:
                _LOGGER.debug("%s - Command response received!", log_prefix)
            else:
                _LOGGER.debug("%s - No command response received", log_prefix)
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.warning("%s - Error sending command: %s", log_prefix, ex)
            _LOGGER.debug(
                "%s - Command error details: %s", log_prefix, traceback.format_exc()
            )

        # Wait a bit longer for more messages to arrive
        if not messages_received:
            _LOGGER.debug("%s - No messages received, waiting longer", log_prefix)
            await asyncio.sleep(3)

        # Clean up
        mqttc.loop_stop()
        try:
            mqttc.disconnect()
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.debug("%s - Disconnect error (ignorable): %s", log_prefix, ex)

        # Check if we received any messages
        messages_count = len(messages_received)
        topics_count = len(topics_found)

        debug_info["messages_received"] = messages_count
        debug_info["topics_found"] = topics_count
        debug_info["topics_list"] = list(topics_found)
        debug_info["responses_received"] = len(responses_received)

        _LOGGER.debug(
            "%s - Test complete. Messages: %d, Topics: %d, Responses: %d",
            log_prefix,
            messages_count,
            topics_count,
            len(responses_received),
        )

        # Even if we didn't receive messages, we'll consider it a success with a warning
        # since MQTT topics might not have data immediately
        return {
            "success": True,
            "details": f"Found {messages_count} messages on {topics_count} topics",
            "debug_info": debug_info,
        }

    except socket.timeout:
        _LOGGER.error("%s - Connection timeout", log_prefix)
        debug_info["error"] = {
            "type": "timeout",
            "message": "Connection timeout",
        }
        return {
            "success": False,
            "error_type": ERROR_TIMEOUT,
            "message": "Connection timeout",
            "details": "Connection to MQTT broker timed out during topic testing",
            "debug_info": debug_info,
        }
    # Fixed exception order
    except ConnectionError as conn_ex:
        _LOGGER.error("%s - Connection error: %s", log_prefix, conn_ex)
        _LOGGER.debug(
            "%s - Connection error details: %s", log_prefix, traceback.format_exc()
        )
        debug_info["error"] = {
            "type": "connection",
            "message": str(conn_ex),
        }
        return {
            "success": False,
            "error_type": ERROR_CANNOT_CONNECT,
            "message": f"Connection error: {conn_ex}",
            "details": f"Connection error during topic testing: {conn_ex}",
            "debug_info": debug_info,
        }
    except TimeoutError as timeout_ex:
        _LOGGER.error("%s - Timeout error: %s", log_prefix, timeout_ex)
        _LOGGER.debug(
            "%s - Timeout error details: %s", log_prefix, traceback.format_exc()
        )
        debug_info["error"] = {
            "type": "timeout",
            "message": str(timeout_ex),
        }
        return {
            "success": False,
            "error_type": ERROR_TIMEOUT,
            "message": f"Timeout error: {timeout_ex}",
            "details": f"Timeout error during topic testing: {timeout_ex}",
            "debug_info": debug_info,
        }
    except socket.error as socket_err:
        _LOGGER.error("%s - Socket error: %s", log_prefix, socket_err)
        _LOGGER.debug(
            "%s - Socket error details: %s", log_prefix, traceback.format_exc()
        )
        debug_info["error"] = {
            "type": "socket",
            "message": str(socket_err),
        }
        return {
            "success": False,
            "error_type": ERROR_CANNOT_CONNECT,
            "message": f"Socket error: {socket_err}",
            "details": f"Socket error during topic testing: {socket_err}",
            "debug_info": debug_info,
        }
    except Exception as ex:  # pylint: disable=broad-except
        _LOGGER.exception("%s - Unexpected error: %s", log_prefix, ex)
        _LOGGER.debug(
            "%s - Unexpected error details: %s", log_prefix, traceback.format_exc()
        )
        debug_info["error"] = {
            "type": "unexpected",
            "message": str(ex),
        }
        return {
            "success": False,
            "error_type": ERROR_UNKNOWN,
            "message": f"Unexpected error: {ex}",
            "details": f"An unexpected error occurred during topic testing: {ex}",
            "debug_info": debug_info,
        }
