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
        
        # Format directly based on the native unit
        if unit == UnitOfTime.DAYS:
            # Extract days, hours, minutes
            days = int(raw_value)
            fractional_day = raw_value - days
            
            if days > 0:
                parts.append(f"{days}d")
                
            # Convert fractional day to hours
            hours = int((fractional_day * 24).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))
            if hours > 0:
                parts.append(f"{hours}h")
                
        elif unit == UnitOfTime.HOURS:
            # Extract hours, minutes
            hours = int(raw_value)
            fractional_hour = raw_value - hours
            
            if hours > 0:
                parts.append(f"{hours}h")
                
            # Convert fractional hour to minutes
            minutes = int((fractional_hour * 60).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))
            if minutes > 0:
                parts.append(f"{minutes}m")
                
        elif unit == UnitOfTime.MINUTES:
            # Extract minutes, seconds
            minutes = int(raw_value)
            fractional_minute = raw_value - minutes
            
            if minutes > 0:
                parts.append(f"{minutes}m")
                
            # Convert fractional minute to seconds
            seconds = int((fractional_minute * 60).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))
            if seconds > 0 or not parts:  # Add seconds if it's the only component
                parts.append(f"{seconds}s")
                
        else:  # Default: SECONDS
            # For seconds, show appropriate components
            total_seconds = raw_value
            
            days, remainder = divmod(total_seconds, 86400)
            if days > 0:
                days = int(days)
                parts.append(f"{days}d")
                
            hours, remainder = divmod(remainder, 3600)
            if hours > 0:
                hours = int(hours)
                parts.append(f"{hours}h")
                
            minutes, seconds = divmod(remainder, 60)
            if minutes > 0:
                minutes = int(minutes)
                parts.append(f"{minutes}m")
                
            # Add seconds if less than an hour total or it's the only component
            if (not parts) or (days == 0 and hours == 0):
                # Format seconds with appropriate precision
                if seconds < 10:
                    seconds = round(float(seconds), 1)
                    parts.append(f"{seconds}s")
                else:
                    seconds = int(seconds.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                    parts.append(f"{seconds}s")

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
        
    # If already a number, return it as is (assuming it's already in target unit)
    if isinstance(value, (int, float)):
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
