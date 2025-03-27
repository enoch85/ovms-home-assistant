"""Duration formatting utilities for OVMS sensors."""
import re
from typing import Any, Optional
from decimal import Decimal, ROUND_HALF_UP

from homeassistant.const import UnitOfTime

# Extended time units
MONTHS = "months"
YEARS = "years"

def format_duration(value, unit=UnitOfTime.SECONDS, use_full_names=False):
    """Format a duration value to a human-readable string based on its native unit.
    
    Args:
        value: The duration value in its native unit
        unit: The unit of the value (UnitOfTime constant or string like 'min', 'seconds')
        use_full_names: If True, use full unit names (e.g., "minutes" instead of "m")
    
    Returns:
        A formatted string representation of the duration
        Short format (e.g., "5d 2h 30m") when use_full_names=False
        Full format (e.g., "5 days 2 hours 30 minutes") when use_full_names=True
    """
    try:
        # Convert to precise decimal for calculations
        raw_value = Decimal(str(value))
        
        # Handle negative values
        is_negative = raw_value < 0
        if is_negative:
            raw_value = abs(raw_value)
        
        # Convert string unit to proper unit type if needed
        if isinstance(unit, str):
            unit_str = unit.lower()
            if unit_str in ["m", "min", "minute", "minutes"]:
                unit = UnitOfTime.MINUTES
            elif unit_str in ["h", "hr", "hour", "hours"]:
                unit = UnitOfTime.HOURS
            elif unit_str in ["d", "day", "days"]:
                unit = UnitOfTime.DAYS
            elif unit_str in ["mo", "month", "months"]:
                unit = MONTHS
            elif unit_str in ["y", "yr", "year", "years"]:
                unit = YEARS
            else:
                unit = UnitOfTime.SECONDS
        
        # Define unit labels based on the use_full_names parameter
        if use_full_names:
            year_label = " year" if int(raw_value) == 1 else " years"
            month_label = " month" if int(raw_value) == 1 else " months"
            day_label = " day" if int(raw_value) == 1 else " days"
            hour_label = " hour" if int(raw_value) == 1 else " hours"
            minute_label = " minute" if int(raw_value) == 1 else " minutes"
            second_label = " second" if int(raw_value) == 1 else " seconds"
        else:
            year_label = "y"
            month_label = "mo"
            day_label = "d"
            hour_label = "h"
            minute_label = "m"
            second_label = "s"
        
        parts = []
        
        # Constants for time conversions
        SECONDS_PER_MINUTE = 60
        MINUTES_PER_HOUR = 60
        HOURS_PER_DAY = 24
        DAYS_PER_MONTH = Decimal('30.44')  # Average days per month (365.25/12)
        MONTHS_PER_YEAR = 12
        
        # Format based on the native unit
        if unit == MONTHS:
            # For months: extract years, months, days
            total_months = raw_value
            
            # Extract years from months
            years = int(total_months // MONTHS_PER_YEAR)
            months = int(total_months % MONTHS_PER_YEAR)
            month_fraction = total_months % 1
            
            if years > 0:
                if use_full_names:
                    year_label = " year" if years == 1 else " years"
                parts.append(f"{years}{year_label}")
            
            if months > 0 or (years > 0 and month_fraction == 0):
                if use_full_names:
                    month_label = " month" if months == 1 else " months"
                parts.append(f"{months}{month_label}")
            
            # Convert fraction of month to days
            days = int(month_fraction * DAYS_PER_MONTH)
            if days > 0 and years == 0:  # Only show days if less than 1 year
                if use_full_names:
                    day_label = " day" if days == 1 else " days"
                parts.append(f"{days}{day_label}")
                
        elif unit == YEARS:
            # For years: extract years, months, days
            whole_years = int(raw_value)
            year_fraction = raw_value - whole_years
            
            if whole_years > 0:
                if use_full_names:
                    year_label = " year" if whole_years == 1 else " years"
                parts.append(f"{whole_years}{year_label}")
            
            # Convert fraction of year to months
            months = int(year_fraction * MONTHS_PER_YEAR)
            month_fraction = (year_fraction * MONTHS_PER_YEAR) - months
            
            if months > 0 or whole_years > 0:
                if use_full_names:
                    month_label = " month" if months == 1 else " months"
                parts.append(f"{months}{month_label}")
            
            # Convert fraction of month to days
            days = int(month_fraction * DAYS_PER_MONTH)
            if days > 0 and whole_years == 0:  # Only show days if less than 1 year
                if use_full_names:
                    day_label = " day" if days == 1 else " days"
                parts.append(f"{days}{day_label}")
                
        elif unit == UnitOfTime.MINUTES:
            # For minutes: extract hours, minutes, seconds
            total_minutes = raw_value
            
            # Extract hours from minutes
            hours = int(total_minutes // MINUTES_PER_HOUR)
            minutes = int(total_minutes % MINUTES_PER_HOUR)
            minute_fraction = total_minutes % 1
            
            if hours > 0:
                if use_full_names:
                    hour_label = " hour" if hours == 1 else " hours"
                parts.append(f"{hours}{hour_label}")
            
            if minutes > 0 or (hours > 0 and minute_fraction == 0):
                if use_full_names:
                    minute_label = " minute" if minutes == 1 else " minutes"
                parts.append(f"{minutes}{minute_label}")
            
            # Convert fraction of minute to seconds
            seconds = int(minute_fraction * SECONDS_PER_MINUTE)
            if seconds > 0 and hours == 0:  # Only show seconds if less than 1 hour
                if use_full_names:
                    second_label = " second" if seconds == 1 else " seconds"
                parts.append(f"{seconds}{second_label}")
                
        elif unit == UnitOfTime.HOURS:
            # For hours: extract hours, minutes, seconds
            whole_hours = int(raw_value)
            hour_fraction = raw_value - whole_hours
            
            if whole_hours > 0:
                if use_full_names:
                    hour_label = " hour" if whole_hours == 1 else " hours"
                parts.append(f"{whole_hours}{hour_label}")
            
            # Convert fraction of hour to minutes
            minutes = int(hour_fraction * MINUTES_PER_HOUR)
            minute_fraction = (hour_fraction * MINUTES_PER_HOUR) - minutes
            
            if minutes > 0 or whole_hours > 0:
                if use_full_names:
                    minute_label = " minute" if minutes == 1 else " minutes"
                parts.append(f"{minutes}{minute_label}")
            
            # Convert fraction of minute to seconds
            seconds = int(minute_fraction * SECONDS_PER_MINUTE)
            if seconds > 0 and whole_hours == 0:  # Only show seconds if less than 1 hour
                if use_full_names:
                    second_label = " second" if seconds == 1 else " seconds"
                parts.append(f"{seconds}{second_label}")
                
        elif unit == UnitOfTime.DAYS:
            # For days: extract days, hours, minutes
            whole_days = int(raw_value)
            day_fraction = raw_value - whole_days
            
            if whole_days > 0:
                if use_full_names:
                    day_label = " day" if whole_days == 1 else " days"
                parts.append(f"{whole_days}{day_label}")
            
            # Convert fraction of day to hours
            hours = int(day_fraction * HOURS_PER_DAY)
            hour_fraction = (day_fraction * HOURS_PER_DAY) - hours
            
            if hours > 0 or whole_days > 0:
                if use_full_names:
                    hour_label = " hour" if hours == 1 else " hours"
                parts.append(f"{hours}{hour_label}")
            
            # Convert fraction of hour to minutes
            minutes = int(hour_fraction * MINUTES_PER_HOUR)
            if minutes > 0 or hours > 0 or whole_days > 0:
                if use_full_names:
                    minute_label = " minute" if minutes == 1 else " minutes"
                parts.append(f"{minutes}{minute_label}")
                
        else:  # Default: SECONDS
            # For seconds: extract years, months, days, hours, minutes, seconds
            total_seconds = raw_value
            
            days = int(total_seconds // (SECONDS_PER_MINUTE * MINUTES_PER_HOUR * HOURS_PER_DAY))
            remainder = total_seconds % (SECONDS_PER_MINUTE * MINUTES_PER_HOUR * HOURS_PER_DAY)
            
            # If more than 60 days, convert to months and years
            if days >= 60:
                months = int(days // DAYS_PER_MONTH)
                remaining_days = days % DAYS_PER_MONTH
                
                # If more than 12 months, convert to years
                if months >= 12:
                    years = int(months // MONTHS_PER_YEAR)
                    remaining_months = months % MONTHS_PER_YEAR
                    
                    if use_full_names:
                        year_label = " year" if years == 1 else " years"
                    parts.append(f"{years}{year_label}")
                    
                    if remaining_months > 0:
                        if use_full_names:
                            month_label = " month" if remaining_months == 1 else " months"
                        parts.append(f"{remaining_months}{month_label}")
                else:
                    if use_full_names:
                        month_label = " month" if months == 1 else " months"
                    parts.append(f"{months}{month_label}")
                
                if remaining_days > 0:
                    if use_full_names:
                        day_label = " day" if remaining_days == 1 else " days"
                    parts.append(f"{remaining_days}{day_label}")
                
                # Don't show hours/minutes/seconds for durations longer than 60 days
            else:
                # Standard days/hours/minutes/seconds format
                if days > 0:
                    if use_full_names:
                        day_label = " day" if days == 1 else " days"
                    parts.append(f"{days}{day_label}")
                
                hours = int(remainder // (SECONDS_PER_MINUTE * MINUTES_PER_HOUR))
                remainder = remainder % (SECONDS_PER_MINUTE * MINUTES_PER_HOUR)
                
                if hours > 0 or days > 0:
                    if use_full_names:
                        hour_label = " hour" if hours == 1 else " hours"
                    parts.append(f"{hours}{hour_label}")
                
                minutes = int(remainder // SECONDS_PER_MINUTE)
                seconds = remainder % SECONDS_PER_MINUTE
                
                if minutes > 0 or hours > 0 or days > 0:
                    if use_full_names:
                        minute_label = " minute" if minutes == 1 else " minutes"
                    parts.append(f"{minutes}{minute_label}")
                
                # Only include seconds if less than 1 hour total or it's the only component
                if (not parts) or (days == 0 and hours == 0):
                    # Format seconds with appropriate precision
                    if seconds < 10:
                        seconds_rounded = float(seconds.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))
                        if use_full_names:
                            second_label = " second" if seconds_rounded == 1 else " seconds"
                        parts.append(f"{seconds_rounded}{second_label}")
                    else:
                        seconds_int = int(seconds.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                        if use_full_names:
                            second_label = " second" if seconds_int == 1 else " seconds"
                        parts.append(f"{seconds_int}{second_label}")
        
        # Handle empty parts (zero value)
        if not parts:
            if unit == UnitOfTime.SECONDS:
                parts = [f"0{second_label}"]
            elif unit == UnitOfTime.MINUTES:
                parts = [f"0{minute_label}"]
            elif unit == UnitOfTime.HOURS:
                parts = [f"0{hour_label}"]
            elif unit == UnitOfTime.DAYS:
                parts = [f"0{day_label}"]
            elif unit == MONTHS:
                parts = [f"0{month_label}"]
            elif unit == YEARS:
                parts = [f"0{year_label}"]
        
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
    """Parse duration value from formatted string to the target unit.

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
                    total_seconds = hours * 3600 + minutes * 60 + seconds
                    # Convert to target unit
                    if target_unit == UnitOfTime.MINUTES:
                        return total_seconds / 60
                    elif target_unit == UnitOfTime.HOURS:
                        return total_seconds / 3600
                    elif target_unit == UnitOfTime.DAYS:
                        return total_seconds / 86400
                    elif target_unit == MONTHS:
                        return total_seconds / (86400 * 30.44)
                    elif target_unit == YEARS:
                        return total_seconds / (86400 * 365.25)
                    return total_seconds
                except ValueError:
                    pass
            elif len(parts) == 2:  # MM:SS
                try:
                    minutes, seconds = map(float, parts)
                    total_seconds = minutes * 60 + seconds
                    # Convert to target unit
                    if target_unit == UnitOfTime.MINUTES:
                        return total_seconds / 60
                    elif target_unit == UnitOfTime.HOURS:
                        return total_seconds / 3600
                    elif target_unit == UnitOfTime.DAYS:
                        return total_seconds / 86400
                    elif target_unit == MONTHS:
                        return total_seconds / (86400 * 30.44)
                    elif target_unit == YEARS:
                        return total_seconds / (86400 * 365.25)
                    return total_seconds
                except ValueError:
                    pass

        # Handle formatted duration strings like "2h 30m" or "2 hours 30 minutes"
        try:
            # Match patterns for various formats with both short and full unit names
            total_seconds = 0

            # Parse years
            year_match = re.search(r'(\d+\.?\d*)\s*(y|years?)', value, re.IGNORECASE)
            if year_match:
                total_seconds += float(year_match.group(1)) * 86400 * 365.25

            # Parse months
            month_match = re.search(r'(\d+\.?\d*)\s*(mo|months?)', value, re.IGNORECASE)
            if month_match:
                total_seconds += float(month_match.group(1)) * 86400 * 30.44

            # Parse days
            day_match = re.search(r'(\d+\.?\d*)\s*(d|days?)', value, re.IGNORECASE)
            if day_match:
                total_seconds += float(day_match.group(1)) * 86400

            # Parse hours
            hour_match = re.search(r'(\d+\.?\d*)\s*(h|hours?)', value, re.IGNORECASE)
            if hour_match:
                total_seconds += float(hour_match.group(1)) * 3600

            # Parse minutes
            minute_match = re.search(r'(\d+\.?\d*)\s*(m(?!o)|min|minutes?)', value, re.IGNORECASE)
            if minute_match:
                total_seconds += float(minute_match.group(1)) * 60

            # Parse seconds
            second_match = re.search(r'(\d+\.?\d*)\s*(s|seconds?)', value, re.IGNORECASE)
            if second_match:
                total_seconds += float(second_match.group(1))

            if total_seconds > 0 or any([year_match, month_match, day_match, hour_match, minute_match, second_match]):
                # Convert to target unit
                if target_unit == UnitOfTime.MINUTES:
                    return total_seconds / 60
                elif target_unit == UnitOfTime.HOURS:
                    return total_seconds / 3600
                elif target_unit == UnitOfTime.DAYS:
                    return total_seconds / 86400
                elif target_unit == MONTHS:
                    return total_seconds / (86400 * 30.44)
                elif target_unit == YEARS:
                    return total_seconds / (86400 * 365.25)
                return total_seconds
        except Exception:
            pass

    # If all parsing fails, return None
    return None
