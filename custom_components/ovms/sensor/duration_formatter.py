"""Duration formatting utilities for OVMS sensors."""
import re
from typing import Any, Optional

def format_duration(seconds_value):
    """Format a duration value in seconds to a human-readable string."""
    try:
        # Convert to number of seconds
        seconds = float(seconds_value)

        # Handle negative values
        is_negative = seconds < 0
        if is_negative:
            seconds = abs(seconds)

        # Break down into components
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        # Format with appropriate precision
        parts = []
        if days > 0:
            parts.append(f"{int(days)}d")
        if hours > 0 or days > 0:
            parts.append(f"{int(hours)}h")
        if minutes > 0 or hours > 0 or days > 0:
            parts.append(f"{int(minutes)}m")

        # Only include seconds if less than 1 hour total duration
        # or if it's the only component
        if len(parts) == 0 or (days == 0 and hours == 0):
            # Round seconds for better readability
            if seconds < 10:
                parts.append(f"{seconds:.1f}s")
            else:
                parts.append(f"{int(round(seconds))}s")

        # Combine all parts
        formatted = " ".join(parts)

        # Add negative sign if needed
        if is_negative:
            formatted = "-" + formatted

        return formatted
    except (ValueError, TypeError):
        # Return original value if it can't be parsed
        return str(seconds_value)

def parse_duration(value: Any) -> Optional[float]:
    """Parse duration value from either seconds or formatted string.

    This function can convert both numeric seconds and formatted strings
    like "2h 30m" into a standard seconds value.
    """
    if not value:
        return None

    # If it's already a number, return it
    if isinstance(value, (int, float)):
        return float(value)

    # If it's a string that represents a number, convert it
    if isinstance(value, str):
        # Direct numeric conversion
        try:
            return float(value)
        except ValueError:
            pass

        # Handle HH:MM:SS format
        if ":" in value:
            parts = value.split(":")
            if len(parts) == 3:  # HH:MM:SS
                try:
                    hours, minutes, seconds = map(float, parts)
                    return hours * 3600 + minutes * 60 + seconds
                except ValueError:
                    pass
            elif len(parts) == 2:  # MM:SS
                try:
                    minutes, seconds = map(float, parts)
                    return minutes * 60 + seconds
                except ValueError:
                    pass

        # Handle formatted duration strings like "2h 30m"
        try:
            # Match patterns like 1d, 2h, 30m, 45s
            total_seconds = 0

            # Days
            day_match = re.search(r'(\d+)d', value)
            if day_match:
                total_seconds += int(day_match.group(1)) * 86400

            # Hours
            hour_match = re.search(r'(\d+)h', value)
            if hour_match:
                total_seconds += int(hour_match.group(1)) * 3600

            # Minutes
            minute_match = re.search(r'(\d+)m', value)
            if minute_match:
                total_seconds += int(minute_match.group(1)) * 60

            # Seconds
            second_match = re.search(r'(\d+\.?\d*)s', value)
            if second_match:
                total_seconds += float(second_match.group(1))

            if total_seconds > 0 or (day_match or hour_match or minute_match or second_match):
                return total_seconds
        except Exception:
            pass

    # If all parsing fails, return None
    return None
