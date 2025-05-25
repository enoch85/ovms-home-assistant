#!/usr/bin/env python3
"""Test script to validate tire pressure parsing functionality."""

import sys
from typing import Any, Optional

# Mock the Home Assistant imports
class MockSensorDeviceClass:
    PRESSURE = "pressure"

class MockUnitOfPressure:
    KPA = "kPa"
    PSI = "psi"
    BAR = "bar"

# Simple pressure conversion function
def convert_pressure(value: float, from_unit: str, to_unit: str) -> float:
    """Convert pressure between units."""
    # Convert to kPa first (as base unit)
    base_value = value
    if from_unit.lower() == "psi":
        base_value = value * 6.89476  # 1 PSI = 6.89476 kPa
    elif from_unit.lower() == "bar":
        base_value = value * 100  # 1 bar = 100 kPa
    
    # Then convert to target unit
    if to_unit == MockUnitOfPressure.KPA:
        return base_value
    elif to_unit == MockUnitOfPressure.PSI:
        return base_value / 6.89476
    elif to_unit == MockUnitOfPressure.BAR:
        return base_value / 100
    
    return base_value

def test_pressure_parsing(value: str, device_class: Optional[Any] = None) -> Any:
    """Test the pressure parsing logic."""
    
    # Extract unit detection logic
    value_without_unit = value
    unit_suffix = ""
    
    if isinstance(value, str):
        pressure_units = ["psi", "kpa", "bar"]
        for unit in pressure_units:
            if value.lower().endswith(unit):
                unit_suffix = value[-len(unit):].lower()
                value_without_unit = value[:-len(unit)]
                break
    
    # Check if this is a separator-based list (comma or semicolon separated) of numbers
    if isinstance(value_without_unit, str) and ("," in value_without_unit or ";" in value_without_unit):
        try:
            # Determine the separator
            separator = ";" if ";" in value_without_unit else ","
            
            # Handling for tire pressure values
            if device_class == MockSensorDeviceClass.PRESSURE:
                print(f"DEBUG: Processing tire pressure values for string: '{value_without_unit}'")
                
                parsed_floats = []
                all_parts_valid = True
                # Split the string into potential parts, stripping whitespace and removing empty parts
                potential_parts = [p.strip() for p in value_without_unit.split(separator) if p.strip()]

                if not potential_parts:
                    print(f"DEBUG: No valid parts found after splitting and stripping: '{value_without_unit}'")
                    all_parts_valid = False
                else:
                    for part_str in potential_parts:
                        try:
                            parsed_floats.append(float(part_str))
                        except (ValueError, TypeError):
                            print(f"DEBUG: Failed to parse '{part_str}' as float in pressure-specific block.")
                            all_parts_valid = False
                            break
                
                if all_parts_valid and parsed_floats:
                    print(f"DEBUG: Successfully parsed all pressure parts: {parsed_floats} from '{value_without_unit}'")
                    
                    # Unit conversion if necessary (e.g., psi to kPa)
                    if unit_suffix == "psi":
                        parsed_floats = [convert_pressure(p, "psi", MockUnitOfPressure.KPA) for p in parsed_floats]
                        print(f"DEBUG: Converted PSI pressure parts to KPA: {parsed_floats}")
                    
                    avg_value = sum(parsed_floats) / len(parsed_floats)
                    result = round(avg_value, 4)
                    print(f"DEBUG: Calculated pressure result: {result} from parts: {parsed_floats}")
                    return {
                        "value": result,
                        "raw_values": parsed_floats,
                        "unit": MockUnitOfPressure.KPA if unit_suffix == "psi" else unit_suffix or MockUnitOfPressure.KPA,
                        "count": len(parsed_floats),
                        "min": min(parsed_floats),
                        "max": max(parsed_floats)
                    }
                else:
                    print(f"DEBUG: Falling through from pressure-specific block for: '{value_without_unit}'")
        
        except Exception as e:
            print(f"ERROR: Error during pressure parsing: {e}")
    
    # Fallback to original value
    print(f"DEBUG: Returning original value: {value}")
    return value

def main():
    """Test various tire pressure parsing scenarios."""
    print("Testing OVMS Tire Pressure Parsing")
    print("=" * 40)
    
    test_cases = [
        # PSI values
        ("32,33,31,32psi", MockSensorDeviceClass.PRESSURE),
        ("32.5,33.1,31.8,32.2psi", MockSensorDeviceClass.PRESSURE),
        ("30; 31; 29; 30psi", MockSensorDeviceClass.PRESSURE),
        
        # KPA values
        ("220,225,215,220kpa", MockSensorDeviceClass.PRESSURE),
        ("220.5,225.1,215.8,220.2kpa", MockSensorDeviceClass.PRESSURE),
        
        # BAR values
        ("2.2,2.25,2.15,2.2bar", MockSensorDeviceClass.PRESSURE),
        
        # No unit
        ("32,33,31,32", MockSensorDeviceClass.PRESSURE),
        
        # Invalid cases
        ("invalid,data,here", MockSensorDeviceClass.PRESSURE),
        ("32,,31,", MockSensorDeviceClass.PRESSURE),
        ("", MockSensorDeviceClass.PRESSURE),
        
        # Single values
        ("32psi", MockSensorDeviceClass.PRESSURE),
        ("220kpa", MockSensorDeviceClass.PRESSURE),
        
        # Mixed scenarios
        ("32.0, 33.5 , 31.2, 32.8psi", MockSensorDeviceClass.PRESSURE),  # Extra spaces
    ]
    
    for i, (test_value, device_class) in enumerate(test_cases, 1):
        print(f"\nTest {i}: '{test_value}'")
        print("-" * 30)
        
        try:
            result = test_pressure_parsing(test_value, device_class)
            if isinstance(result, dict):
                print(f"✓ Parsed successfully:")
                print(f"  Average: {result['value']}")
                print(f"  Raw values: {result['raw_values']}")
                print(f"  Unit: {result['unit']}")
                print(f"  Count: {result['count']}")
                print(f"  Range: {result['min']} - {result['max']}")
            else:
                print(f"✗ Fallback result: {result}")
        except Exception as e:
            print(f"✗ Error: {e}")

if __name__ == "__main__":
    main()
