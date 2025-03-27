"""Duration formatting utilities for OVMS sensors."""
import re
from typing import Any, Optional
from decimal import Decimal, ROUND_HALF_UP

from homeassistant.const import UnitOfTime

def format_duration(value, unit=UnitOfTime.SECONDS):
    """Format a duration value to a human-readable string based on its native unit.
    
    Args:
        value: The duration value in its native unit
        unit: The native unit of the value (UnitOfTime constant)
    
    Returns:
        A formatted string representation of the duration
    """
    try:
        # Convert to precise decimal for calculations
        raw_value = Decimal(str(value))
        
        # Handle negative values
        is_negative = raw_value < 0
        if is_negative:
            raw_value = abs(raw_value)
        
        parts = []
        
        # Format directly based on the native unit without converting to seconds
        if unit == UnitOfTime.DAYS:
            # For days: extract days, hours, minutes
            whole_days = int(raw_value)
            day_fraction = raw_value - whole_days
            
            if whole_days > 0:
                parts.append(f"{whole_days}d")
            
            # Convert fraction of day to hours
            hours = int(day_fraction * 24)
            hour_fraction = (day_fraction * 24) - hours
            
            if hours > 0 or whole_days > 0:
                parts.append(f"{hours}h")
            
            # Convert fraction of hour to minutes
            minutes = int(hour_fraction * 60)
            if minutes > 0 or hours > 0 or whole_days > 0:
                parts.append(f"{minutes}m")
                
        elif unit == UnitOfTime.HOURS:
            # For hours: extract hours, minutes, seconds
            whole_hours = int(raw_value)
            hour_fraction = raw_value - whole_hours
            
            if whole_hours > 0:
                parts.append(f"{whole_hours}h")
            
            # Convert fraction of hour to minutes
            minutes = int(hour_fraction * 60)
            minute_fraction = (hour_fraction * 60) - minutes
            
            if minutes > 0 or whole_hours > 0:
                parts.append(f"{minutes}m")
            
            # Convert fraction of minute to seconds
            seconds = int(minute_fraction * 60)
            if seconds > 0 and (whole_hours == 0):  # Only show seconds if less than 1 hour
                parts.append(f"{seconds}s")
                
        elif unit == UnitOfTime.MINUTES:
            # For minutes: extract hours, minutes, seconds
            total_minutes = raw_value
            
            # Extract hours from minutes
            hours = int(total_minutes // 60)
            minutes = int(total_minutes % 60)
            minute_fraction = total_minutes % 1
            
            if hours > 0:
                parts.append(f"{hours}h")
            
            if minutes > 0 or hours > 0:
                parts.append(f"{minutes}m")
            
            # Convert fraction of minute to seconds
            seconds = int(minute_fraction * 60)
            if seconds > 0 and (hours == 0):  # Only show seconds if less than 1 hour
                parts.append(f"{seconds}s")
                
        else:  # Default: SECONDS
            # For seconds: extract days, hours, minutes, seconds
            total_seconds = raw_value
            
            # Extract components
            days = int(total_seconds // 86400)
            remainder = total_seconds % 86400
            
            hours = int(remainder // 3600)
            remainder = remainder % 3600
            
            minutes = int(remainder // 60)
            seconds = remainder % 60
            
            if days > 0:
                parts.append(f"{days}d")
            
            if hours > 0 or days > 0:
                parts.append(f"{hours}h")
            
            if minutes > 0 or hours > 0 or days > 0:
                parts.append(f"{minutes}m")
            
            # Only include seconds if less than 1 hour total or it's the only component
            if (not parts) or (days == 0 and hours == 0):
                # Format seconds with appropriate precision
                if seconds < 10:
                    seconds_rounded = float(seconds.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))
                    parts.append(f"{seconds_rounded}s")
                else:
                    seconds_int = int(seconds.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                    parts.append(f"{seconds_int}s")
        
        # Handle empty parts (zero value)
        if not parts:
            if unit == UnitOfTime.SECONDS:
                parts = ["0s"]
            elif unit == UnitOfTime.MINUTES:
                parts = ["0m"]
            elif unit == UnitOfTime.HOURS:
                parts = ["0h"]
            elif unit == UnitOfTime.DAYS:
                parts = ["0d"]
        
        # Join parts with spaces
        formatted = " ".join(parts)
        
        # Add negative sign if needed
        if is_negative:
            formatted = "-" + formatted
            
        return formatted
        
    except (ValueError, TypeError):
        # Return original value if it can't be parsed
        return str(value)

def parse_duration(value: Any, target_unit=UnitOfTime.SECONDS) -> Optional[float]:
    """Parse duration value from formatted string to the target unit."""
    if value is None:
        return None
        
    # If already a number, return it converted to target unit
    if isinstance(value, (int, float)):
        # For direct numbers, assume they're already in the target unit
        return float(value)
        
    if not isinstance(value, str):
        return None
        
    # Try direct conversion for simple numeric strings
    try:
        return float(value)
    except ValueError:
        pass
        
    # For formatted strings, parse and calculate total in the target unit
    total_in_seconds = 0
    
    # Parse days
    day_match = re.search(r'(\d+\.?\d*)d', value)
    if day_match:
        total_in_seconds += float(day_match.group(1)) * 86400
        
    # Parse hours
    hour_match = re.search(r'(\d+\.?\d*)h', value)
    if hour_match:
        total_in_seconds += float(hour_match.group(1)) * 3600
        
    # Parse minutes
    minute_match = re.search(r'(\d+\.?\d*)m', value)
    if minute_match:
        total_in_seconds += float(minute_match.group(1)) * 60
        
    # Parse seconds
    second_match = re.search(r'(\d+\.?\d*)s', value)
    if second_match:
        total_in_seconds += float(second_match.group(1))
        
    # If we found any time components
    if day_match or hour_match or minute_match or second_match:
        # Convert to target unit
        if target_unit == UnitOfTime.MINUTES:
            return total_in_seconds / 60
        elif target_unit == UnitOfTime.HOURS:
            return total_in_seconds / 3600
        elif target_unit == UnitOfTime.DAYS:
            return total_in_seconds / 86400
        else:  # Default to seconds
            return total_in_seconds
            
    # Handle HH:MM:SS format
    if ":" in value:
        parts = value.split(":")
        if len(parts) == 3:  # HH:MM:SS
            try:
                hours, minutes, seconds = map(float, parts)
                total_in_seconds = hours * 3600 + minutes * 60 + seconds
            except ValueError:
                return None
        elif len(parts) == 2:  # MM:SS
            try:
                minutes, seconds = map(float, parts)
                total_in_seconds = minutes * 60 + seconds
            except ValueError:
                return None
                
        # Convert to target unit
        if target_unit == UnitOfTime.MINUTES:
            return total_in_seconds / 60
        elif target_unit == UnitOfTime.HOURS:
            return total_in_seconds / 3600
        elif target_unit == UnitOfTime.DAYS:
            return total_in_seconds / 86400
        else:  # Default to seconds
            return total_in_seconds
            
    # Could not parse the value
    return None
