# OVMS Tire Position Mapping Enhancement

## Overview

This enhancement implements tire-specific position labeling for the OVMS Home Assistant integration, replacing generic `cell_1`, `cell_2`, etc. names with meaningful tire position labels based on the OVMS standard.

## Key Features

### 1. Tire Position Standard
Based on OVMS TPMS documentation, tire data follows this positional order:
- **Position 0**: Front Left (FL)
- **Position 1**: Front Right (FR)  
- **Position 2**: Rear Left (LR)
- **Position 3**: Rear Right (RR)

### 2. Enhanced Parser
The `parse_comma_separated_values()` function now:
- Detects tire sensors automatically
- Provides both descriptive and short-code position labels
- Maintains backward compatibility with generic cell naming for non-tire sensors

### 3. Tire Sensor Detection
The new `is_tire_sensor()` function identifies tire sensors by:
- **Pressure sensors**: All pressure sensors are assumed to be tire-related
- **Temperature sensors**: Only when category equals "tire"

## Implementation Details

### Attribute Names Generated

For tire sensors (pressure and temperature), the parser now creates these attributes:

#### Descriptive Names
- `tire_front_left`: Front left tire value
- `tire_front_right`: Front right tire value  
- `tire_rear_left`: Rear left tire value
- `tire_rear_right`: Rear right tire value

#### Short Codes
- `tire_fl`: Front left tire value
- `tire_fr`: Front right tire value
- `tire_lr`: Rear left tire value
- `tire_rr`: Rear right tire value

#### Statistics (unchanged)
- `tire_values`: Array of all tire values
- `mean`: Average value across all tires
- `median`: Median value across all tires
- `min`: Minimum tire value
- `max`: Maximum tire value
- `count`: Number of tires

### Example Data Processing

**Input**: `"206.8,216.4,210.2,218.5"` (tire pressures in kPa)

**Output attributes**:
```json
{
  "tire_front_left": 206.8,
  "tire_front_right": 216.4,
  "tire_rear_left": 210.2,
  "tire_rear_right": 218.5,
  "tire_fl": 206.8,
  "tire_fr": 216.4,
  "tire_lr": 210.2,
  "tire_rr": 218.5,
  "tire_values": [206.8, 216.4, 210.2, 218.5],
  "mean": 212.075,
  "median": 213.3,
  "min": 206.8,
  "max": 218.5,
  "count": 4
}
```

## Files Modified

### `/custom_components/ovms/sensor/parsers.py`
- Added `is_tire_sensor()` function for tire sensor detection
- Enhanced `parse_comma_separated_values()` with tire position mapping
- Updated both parser call locations to use tire detection

### `/custom_components/ovms/sensor/factory.py`  
- Enhanced `create_cell_sensors()` with tire position-aware naming
- Added tire-specific attributes for individual sensor creation
- Maintains generic naming for non-tire sensors

## Backward Compatibility

- **Generic sensors**: Continue to use `cell_1`, `cell_2`, etc. naming
- **Existing functionality**: All current features remain unchanged
- **Statistics**: Standard statistics (mean, median, etc.) continue to work
- **API compatibility**: No breaking changes to existing sensor interfaces

## Benefits

1. **Meaningful names**: Tire positions are now clearly labeled (Front Left, etc.)
2. **OVMS standard compliance**: Follows official OVMS tire position convention
3. **Dual naming**: Provides both descriptive names and short codes
4. **Generic compatibility**: Non-tire sensors continue to work as before
5. **Ready for 200+ topics**: Generic parser architecture supports any sensor type