"""Utility functions for OVMS metrics."""

from .patterns import TOPIC_PATTERNS

# Placeholders for initial definition to avoid circular imports
# These will be populated on first use
METRIC_DEFINITIONS = None
CATEGORY_BATTERY = None
CATEGORY_CHARGING = None
CATEGORY_CLIMATE = None
CATEGORY_DOOR = None
CATEGORY_LOCATION = None
CATEGORY_MOTOR = None
CATEGORY_TRIP = None
CATEGORY_DIAGNOSTIC = None
CATEGORY_POWER = None
CATEGORY_NETWORK = None
CATEGORY_SYSTEM = None
CATEGORY_TIRE = None
CATEGORY_VW_EUP = None
PREFIX_CATEGORIES = None

def get_metric_by_path(metric_path):
    """Get metric definition by exact path match."""
    global METRIC_DEFINITIONS
    if METRIC_DEFINITIONS is None:
        # Import only when needed
        from . import METRIC_DEFINITIONS as MD
        METRIC_DEFINITIONS = MD

    # First try exact match
    if metric_path in METRIC_DEFINITIONS:
        return METRIC_DEFINITIONS[metric_path]

    # For VW eUP metrics, also try removing 'metric.' prefix if it's present
    if metric_path.startswith('metric.xvu.'):
        alt_path = metric_path[7:]  # Remove 'metric.'
        if alt_path in METRIC_DEFINITIONS:
            return METRIC_DEFINITIONS[alt_path]

    # Try with just 'xvu.' if it exists in the path
    if 'xvu.' in metric_path and not metric_path.startswith('xvu.'):
        xvu_index = metric_path.find('xvu.')
        alt_path = metric_path[xvu_index:]
        if alt_path in METRIC_DEFINITIONS:
            return METRIC_DEFINITIONS[alt_path]

    return None


def get_metric_by_pattern(topic_parts):
    """Try to match a metric by pattern in topic parts."""
    # First, try to find an exact match of the last path component
    if topic_parts:
        last_part = topic_parts[-1].lower()
        for pattern, info in TOPIC_PATTERNS.items():
            if pattern == last_part:
                return info

        # Check for VW eUP metrics specifically
        for part in topic_parts:
            if part == "xvu":
                # This is a VW eUP metric, try to construct a matching key
                metric_key = ".".join(topic_parts)
                global METRIC_DEFINITIONS
                if METRIC_DEFINITIONS is None:
                    # Import only when needed
                    from . import METRIC_DEFINITIONS as MD
                    METRIC_DEFINITIONS = MD

                # Try several variations to handle different path formats
                variations = [
                    metric_key,
                    f"xvu.{metric_key.split('xvu.', 1)[1]}" if 'xvu.' in metric_key else None,
                    ".".join(topic_parts[topic_parts.index("xvu"):])
                ]

                for variation in variations:
                    if variation and variation in METRIC_DEFINITIONS:
                        return METRIC_DEFINITIONS[variation]
                break

    # Then try partial matches in topic parts
    for pattern, info in TOPIC_PATTERNS.items():
        if any(pattern in part.lower() for part in topic_parts):
            return info

    return None


def determine_category_from_topic(topic_parts):
    """Determine the most likely category from topic parts."""
    global CATEGORY_BATTERY, CATEGORY_CHARGING, CATEGORY_CLIMATE, CATEGORY_DOOR
    global CATEGORY_LOCATION, CATEGORY_MOTOR, CATEGORY_TRIP, CATEGORY_DIAGNOSTIC
    global CATEGORY_POWER, CATEGORY_NETWORK, CATEGORY_SYSTEM, CATEGORY_TIRE
    global CATEGORY_VW_EUP, PREFIX_CATEGORIES

    # Initialize categories if not already done
    if CATEGORY_BATTERY is None:
        from . import (
            CATEGORY_BATTERY, CATEGORY_CHARGING, CATEGORY_CLIMATE, CATEGORY_DOOR,
            CATEGORY_LOCATION, CATEGORY_MOTOR, CATEGORY_TRIP, CATEGORY_DIAGNOSTIC,
            CATEGORY_POWER, CATEGORY_NETWORK, CATEGORY_SYSTEM, CATEGORY_TIRE,
            CATEGORY_VW_EUP, PREFIX_CATEGORIES
        )

    # Special handling for VW eUP topics
    if "xvu" in topic_parts:
        return CATEGORY_VW_EUP

    # Check for known categories in topic
    for part in topic_parts:
        part_lower = part.lower()
        if part_lower in [
            CATEGORY_BATTERY,
            CATEGORY_CHARGING,
            CATEGORY_CLIMATE,
            CATEGORY_DOOR,
            CATEGORY_LOCATION,
            CATEGORY_MOTOR,
            CATEGORY_TRIP,
            CATEGORY_DIAGNOSTIC,
            CATEGORY_POWER,
            CATEGORY_NETWORK,
            CATEGORY_SYSTEM,
            CATEGORY_TIRE,
            CATEGORY_VW_EUP,
        ]:
            return part_lower

    # Try matching by prefix
    full_path = ".".join(topic_parts)
    for prefix, category in PREFIX_CATEGORIES.items():
        if full_path.startswith(prefix):
            return category

    # Default category
    return CATEGORY_SYSTEM


def create_friendly_name(topic_parts, metric_info=None):
    """Create a friendly name from topic parts using metric definitions when available."""
    if not topic_parts:
        return "Unknown"

    # If we have metric info, use its name
    if metric_info and "name" in metric_info:
        return metric_info["name"]

    # Check for VW eUP metrics
    if "xvu" in topic_parts:
        # Format as "VW eUP! Sensor Name"
        last_part = topic_parts[-1].replace("_", " ").title()
        return f"VW eUP! {last_part}"

    # Otherwise, build a name from the last part of the topic
    last_part = topic_parts[-1].replace("_", " ").title()

    # Return just the last part without category
    return last_part
