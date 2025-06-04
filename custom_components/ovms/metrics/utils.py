"""Utility functions for OVMS metrics."""

from .patterns import TOPIC_PATTERNS

# Note: Category constants are imported directly in functions to avoid circular import issues

def get_metric_by_path(metric_path):
    """Get metric definition by exact path match."""
    # Import only when needed to avoid circular imports
    from . import METRIC_DEFINITIONS

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

    # For MG ZS-EV metrics, also try removing 'metric.' prefix if it's present
    if metric_path.startswith('metric.xmg.'):
        alt_path = metric_path[7:]  # Remove 'metric.'
        if alt_path in METRIC_DEFINITIONS:
            return METRIC_DEFINITIONS[alt_path]

    # Try with just 'xmg.' if it exists in the path
    if 'xmg.' in metric_path and not metric_path.startswith('xmg.'):
        xmg_index = metric_path.find('xmg.')
        alt_path = metric_path[xmg_index:]
        if alt_path in METRIC_DEFINITIONS:
            return METRIC_DEFINITIONS[alt_path]

    # For Smart ForTwo metrics, also try removing 'metric.' prefix if it's present
    if metric_path.startswith('metric.xsq.'):
        alt_path = metric_path[7:]  # Remove 'metric.'
        if alt_path in METRIC_DEFINITIONS:
            return METRIC_DEFINITIONS[alt_path]

    # Try with just 'xsq.' if it exists in the path
    if 'xsq.' in metric_path and not metric_path.startswith('xsq.'):
        xsq_index = metric_path.find('xsq.')
        alt_path = metric_path[xsq_index:]
        if alt_path in METRIC_DEFINITIONS:
            return METRIC_DEFINITIONS[alt_path]

    # For Nissan Leaf metrics, also try removing 'metric.' prefix if it's present
    if metric_path.startswith('metric.xnl.'):
        alt_path = metric_path[7:]  # Remove 'metric.'
        if alt_path in METRIC_DEFINITIONS:
            return METRIC_DEFINITIONS[alt_path]

    # Try with just 'xnl.' if it exists in the path
    if 'xnl.' in metric_path and not metric_path.startswith('xnl.'):
        xnl_index = metric_path.find('xnl.')
        alt_path = metric_path[xnl_index:]
        if alt_path in METRIC_DEFINITIONS:
            return METRIC_DEFINITIONS[alt_path]

    # For Renault Twizy metrics, also try removing 'metric.' prefix if it's present
    if metric_path.startswith('metric.xrt.'):
        alt_path = metric_path[7:]  # Remove 'metric.'
        if alt_path in METRIC_DEFINITIONS:
            return METRIC_DEFINITIONS[alt_path]

    # Try with just 'xrt.' if it exists in the path
    if 'xrt.' in metric_path and not metric_path.startswith('xrt.'):
        xrt_index = metric_path.find('xrt.')
        alt_path = metric_path[xrt_index:]
        if alt_path in METRIC_DEFINITIONS:
            return METRIC_DEFINITIONS[alt_path]

    return None


def get_metric_by_pattern(topic_parts):
    """Try to match a metric by pattern in topic parts."""
    # Import only when needed to avoid circular imports
    from . import METRIC_DEFINITIONS

    # First, try to find an exact match of the last path component
    if topic_parts:
        last_part = topic_parts[-1].lower()
        for pattern, info in TOPIC_PATTERNS.items():
            if pattern == last_part:
                return info

        # Special case for GPIO patterns that are commonly split across parts
        if len(topic_parts) >= 2:
            # Check for egpio_input and egpio_output patterns
            for i in range(len(topic_parts) - 1):
                combined = f"{topic_parts[i].lower()}_{topic_parts[i+1].lower()}"
                if combined in ["egpio_input", "egpio_output", "egpio_monitor"]:
                    for pattern, info in TOPIC_PATTERNS.items():
                        if pattern == combined:
                            return info

        # Check for VW eUP metrics specifically
        for part in topic_parts:
            if part == "xvu":
                # This is a VW eUP metric, try to construct a matching key
                metric_key = ".".join(topic_parts)

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

        # Check for MG ZS-EV metrics specifically
        for part in topic_parts:
            if part == "xmg":
                # This is an MG ZS-EV metric, try to construct a matching key
                metric_key = ".".join(topic_parts)

                # Try several variations to handle different path formats
                variations = [
                    metric_key,
                    f"xmg.{metric_key.split('xmg.', 1)[1]}" if 'xmg.' in metric_key else None,
                    ".".join(topic_parts[topic_parts.index("xmg"):])
                ]

                for variation in variations:
                    if variation and variation in METRIC_DEFINITIONS:
                        return METRIC_DEFINITIONS[variation]
                break

        # Check for Smart ForTwo metrics specifically
        for part in topic_parts:
            if part == "xsq":
                # This is a Smart ForTwo metric, try to construct a matching key
                metric_key = ".".join(topic_parts)

                # Try several variations to handle different path formats
                variations = [
                    metric_key,
                    f"xsq.{metric_key.split('xsq.', 1)[1]}" if 'xsq.' in metric_key else None,
                    ".".join(topic_parts[topic_parts.index("xsq"):])
                ]

                for variation in variations:
                    if variation and variation in METRIC_DEFINITIONS:
                        return METRIC_DEFINITIONS[variation]
                break

        # Check for Renault Twizy metrics specifically
        for part in topic_parts:
            if part == "xrt":
                # This is a Renault Twizy metric, try to construct a matching key
                metric_key = ".".join(topic_parts)

                # Try several variations to handle different path formats
                variations = [
                    metric_key,
                    f"xrt.{metric_key.split('xrt.', 1)[1]}" if 'xrt.' in metric_key else None,
                    ".".join(topic_parts[topic_parts.index("xrt"):])
                ]

                for variation in variations:
                    if variation and variation in METRIC_DEFINITIONS:
                        return METRIC_DEFINITIONS[variation]
                break

        # Check for Nissan Leaf metrics specifically
        for part in topic_parts:
            if part == "xnl":
                # This is a Nissan Leaf metric, try to construct a matching key
                metric_key = ".".join(topic_parts)

                # Try several variations to handle different path formats
                variations = [
                    metric_key,
                    f"xnl.{metric_key.split('xnl.', 1)[1]}" if 'xnl.' in metric_key else None,
                    ".".join(topic_parts[topic_parts.index("xnl"):])
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
    # Import constants from const.py to maintain single source of truth
    from ..const import (
        CATEGORY_BATTERY, CATEGORY_CHARGING, CATEGORY_CLIMATE, CATEGORY_DOOR,
        CATEGORY_LOCATION, CATEGORY_MOTOR, CATEGORY_TRIP, CATEGORY_DIAGNOSTIC,
        CATEGORY_POWER, CATEGORY_NETWORK, CATEGORY_SYSTEM, CATEGORY_TIRE,
        CATEGORY_VW_EUP, CATEGORY_SMART_FORTWO, CATEGORY_MG_ZS_EV, CATEGORY_NISSAN_LEAF,
        CATEGORY_RENAULT_TWIZY
    )
    # Import PREFIX_CATEGORIES from current module (still defined here)
    from . import PREFIX_CATEGORIES

    import logging
    logger = logging.getLogger(__name__)

    # Special handling for vehicle-specific topics
    if "xvu" in topic_parts:
        return CATEGORY_VW_EUP
    if "xsq" in topic_parts:
        return CATEGORY_SMART_FORTWO
    if "xmg" in topic_parts:
        return CATEGORY_MG_ZS_EV
    if "xnl" in topic_parts:
        return CATEGORY_NISSAN_LEAF
    if "xrt" in topic_parts:
        return CATEGORY_RENAULT_TWIZY

    # Special handling for precise categorization (backup to PREFIX_CATEGORIES)
    full_path = ".".join(topic_parts)

    # Define precise metric categorizations for backup detection
    specific_categorizations = {
        # GPS/Location metrics
        "v.p.altitude": CATEGORY_LOCATION,
        "v.p.direction": CATEGORY_LOCATION,
        "v.p.gpshdop": CATEGORY_LOCATION,
        "v.p.gpslock": CATEGORY_LOCATION,
        "v.p.gpsmode": CATEGORY_LOCATION,
        "v.p.gpssq": CATEGORY_LOCATION,
        "v.p.gpsspeed": CATEGORY_LOCATION,
        "v.p.gpstime": CATEGORY_LOCATION,
        "v.p.latitude": CATEGORY_LOCATION,
        "v.p.longitude": CATEGORY_LOCATION,
        "v.p.satcount": CATEGORY_LOCATION,
        "v.p.location": CATEGORY_LOCATION,
        "v.p.valet.latitude": CATEGORY_LOCATION,
        "v.p.valet.longitude": CATEGORY_LOCATION,

        # Trip metrics from v.p namespace
        "v.p.acceleration": CATEGORY_TRIP,
        "v.p.deceleration": CATEGORY_TRIP,
        "v.p.odometer": CATEGORY_TRIP,
        "v.p.speed": CATEGORY_TRIP,
        "v.p.trip": CATEGORY_TRIP,

        # Climate-specific environment metrics
        "v.e.heating": CATEGORY_CLIMATE,
        "v.e.cooling": CATEGORY_CLIMATE,
        "v.e.hvac": CATEGORY_CLIMATE,
        "v.e.cabin.temp": CATEGORY_CLIMATE,
        "v.e.cabin.fan": CATEGORY_CLIMATE,

        # Motor-specific inverter metrics
        "v.i.temp": CATEGORY_MOTOR,
        "v.i.rpm": CATEGORY_MOTOR,
        "v.i.pwr": CATEGORY_MOTOR,

        # Network-specific metrics
        "m.net.provider": CATEGORY_NETWORK,
        "m.net.sq": CATEGORY_NETWORK,
        "m.net.type": CATEGORY_NETWORK,

        # System-specific metrics
        "m.freeram": CATEGORY_SYSTEM,
        "m.hardware": CATEGORY_SYSTEM,
        "m.serial": CATEGORY_SYSTEM,
        "m.version": CATEGORY_SYSTEM,
    }

    # Check for specific categorization first
    if full_path in specific_categorizations:
        category = specific_categorizations[full_path]
        logger.debug(f"Specific categorization detected - Parts: {topic_parts}, Full Path: {full_path}, Category: {category}")
        return category

    # Try matching by prefix FIRST (this is the primary categorization method)
    for prefix, category in PREFIX_CATEGORIES.items():
        if full_path.startswith(prefix):
            return category

    # Check for known categories in topic parts as fallback
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
            CATEGORY_SMART_FORTWO,
            CATEGORY_MG_ZS_EV,
            CATEGORY_NISSAN_LEAF,
            CATEGORY_RENAULT_TWIZY,
        ]:
            return part_lower

    # Default category
    return CATEGORY_SYSTEM


def create_friendly_name(topic_parts, metric_info=None):
    """Create a friendly name from topic parts using metric definitions when available."""
    if not topic_parts:
        return "Unknown"

    # If we have metric info, use its name
    if metric_info and "name" in metric_info:
        return metric_info["name"]

    # Check for vehicle-specific metrics
    if "xvu" in topic_parts:
        # Format as "VW eUP! Sensor Name"
        last_part = topic_parts[-1].replace("_", " ").title()
        return f"VW eUP! {last_part}"

    # Check for MG ZS-EV metrics
    if "xmg" in topic_parts:
        # Format as "MG ZS-EV Sensor Name"
        last_part = topic_parts[-1].replace("_", " ").title()
        return f"MG ZS-EV {last_part}"

    # Check for Smart ForTwo metrics
    if "xsq" in topic_parts:
        # Format as "Smart ForTwo Sensor Name"
        last_part = topic_parts[-1].replace("_", " ").title()
        return f"Smart ForTwo {last_part}"

    # Check for Nissan Leaf metrics
    if "xnl" in topic_parts:
        # Format as "Nissan Leaf Sensor Name"
        last_part = topic_parts[-1].replace("_", " ").title()
        return f"Nissan Leaf {last_part}"

    # Check for Renault Twizy metrics
    if "xrt" in topic_parts:
        # Format as "Renault Twizy Sensor Name"
        last_part = topic_parts[-1].replace("_", " ").title()
        return f"Renault Twizy {last_part}"

    # Otherwise, build a name from the last part of the topic
    last_part = topic_parts[-1].replace("_", " ").title()

    # Return just the last part without category
    return last_part
