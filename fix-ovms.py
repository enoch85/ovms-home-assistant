#!/usr/bin/env python3
"""
Fix script for OVMS integration issues
This script addresses multiple issues with the OVMS integration:
1. Changes RAM unit from bytes to kilobytes
2. Fixes invalid device classes for Ah units
3. Sets proper signal strength units to dBm
4. Improves timestamp handling

Run this script from your Home Assistant config directory:
python3 fix_ovms.py
"""

import os
import re
import shutil
import sys
from datetime import datetime

# Configuration
BACKUP_DIR = "ovms_backups"
CUSTOM_COMPONENTS_DIR = "custom_components"
OVMS_DIR = os.path.join(CUSTOM_COMPONENTS_DIR, "ovms")

# Files to modify
FILES_TO_MODIFY = {
    # SYSTEM.PY - Fix RAM unit
    "metrics/common/system.py": [
        {
            "search": r'"m\.freeram":\s*{\s*"name":\s*"Free RAM",\s*"description":\s*"Total amount of free RAM in bytes",\s*"icon":\s*"mdi:memory",\s*"device_class":\s*SensorDeviceClass\.DATA_SIZE,\s*"state_class":\s*SensorStateClass\.MEASUREMENT,\s*"unit":\s*UnitOfInformation\.BYTES,\s*"category":\s*"system",\s*"entity_category":\s*EntityCategory\.DIAGNOSTIC,\s*}',
            "replace": '"m.freeram": {\n        "name": "Free RAM",\n        "description": "Total amount of free RAM in kilobytes",\n        "icon": "mdi:memory",\n        "device_class": SensorDeviceClass.DATA_SIZE,\n        "state_class": SensorStateClass.MEASUREMENT,\n        "unit": UnitOfInformation.KILOBYTES,\n        "category": "system",\n        "entity_category": EntityCategory.DIAGNOSTIC,\n    }'
        }
    ],
    
    # BATTERY.PY - Fix Ah device class and state class
    "metrics/common/battery.py": [
        {
            "search": r'"v\.b\.cac":\s*{\s*"name":\s*"Battery Capacity",\s*"description":\s*"Calculated battery pack capacity",\s*"icon":\s*"mdi:battery",\s*"device_class":\s*SensorDeviceClass\.ENERGY_STORAGE,\s*"state_class":\s*SensorStateClass\.MEASUREMENT,\s*"unit":\s*UNIT_AMPERE_HOUR,\s*"category":\s*"battery",\s*}',
            "replace": '"v.b.cac": {\n        "name": "Battery Capacity",\n        "description": "Calculated battery pack capacity",\n        "icon": "mdi:battery",\n        "device_class": None,\n        "state_class": SensorStateClass.MEASUREMENT,\n        "unit": UNIT_AMPERE_HOUR,\n        "category": "battery",\n    }'
        },
        {
            "search": r'"v\.b\.coulomb\.recd":\s*{\s*"name":\s*"Battery Coulomb Recovered Trip",\s*"description":\s*"Main battery coulomb recovered on trip/charge",\s*"icon":\s*"mdi:battery-plus",\s*"device_class":\s*SensorDeviceClass\.ENERGY_STORAGE,\s*"state_class":\s*SensorStateClass\.TOTAL_INCREASING,\s*"unit":\s*UNIT_AMPERE_HOUR,\s*"category":\s*"battery",\s*}',
            "replace": '"v.b.coulomb.recd": {\n        "name": "Battery Coulomb Recovered Trip",\n        "description": "Main battery coulomb recovered on trip/charge",\n        "icon": "mdi:battery-plus",\n        "device_class": None,\n        "state_class": SensorStateClass.TOTAL,\n        "unit": UNIT_AMPERE_HOUR,\n        "category": "battery",\n    }'
        },
        {
            "search": r'"v\.b\.coulomb\.recd\.total":\s*{\s*"name":\s*"Battery Coulomb Recovered Total",\s*"description":\s*"Main battery coulomb recovered total \(life time\)",\s*"icon":\s*"mdi:battery-plus",\s*"device_class":\s*SensorDeviceClass\.ENERGY_STORAGE,\s*"state_class":\s*SensorStateClass\.TOTAL_INCREASING,\s*"unit":\s*UNIT_AMPERE_HOUR,\s*"category":\s*"battery",\s*}',
            "replace": '"v.b.coulomb.recd.total": {\n        "name": "Battery Coulomb Recovered Total",\n        "description": "Main battery coulomb recovered total (life time)",\n        "icon": "mdi:battery-plus",\n        "device_class": None,\n        "state_class": SensorStateClass.TOTAL,\n        "unit": UNIT_AMPERE_HOUR,\n        "category": "battery",\n    }'
        },
        {
            "search": r'"v\.b\.coulomb\.used":\s*{\s*"name":\s*"Battery Coulomb Used Trip",\s*"description":\s*"Main battery coulomb used on trip",\s*"icon":\s*"mdi:battery-minus",\s*"device_class":\s*SensorDeviceClass\.ENERGY_STORAGE,\s*"state_class":\s*SensorStateClass\.TOTAL_INCREASING,\s*"unit":\s*UNIT_AMPERE_HOUR,\s*"category":\s*"battery",\s*}',
            "replace": '"v.b.coulomb.used": {\n        "name": "Battery Coulomb Used Trip",\n        "description": "Main battery coulomb used on trip",\n        "icon": "mdi:battery-minus",\n        "device_class": None,\n        "state_class": SensorStateClass.TOTAL,\n        "unit": UNIT_AMPERE_HOUR,\n        "category": "battery",\n    }'
        },
        {
            "search": r'"v\.b\.coulomb\.used\.total":\s*{\s*"name":\s*"Battery Coulomb Used Total",\s*"description":\s*"Main battery coulomb used total \(life time\)",\s*"icon":\s*"mdi:battery-minus",\s*"device_class":\s*SensorDeviceClass\.ENERGY_STORAGE,\s*"state_class":\s*SensorStateClass\.TOTAL_INCREASING,\s*"unit":\s*UNIT_AMPERE_HOUR,\s*"category":\s*"battery",\s*}',
            "replace": '"v.b.coulomb.used.total": {\n        "name": "Battery Coulomb Used Total",\n        "description": "Main battery coulomb used total (life time)",\n        "icon": "mdi:battery-minus",\n        "device_class": None,\n        "state_class": SensorStateClass.TOTAL,\n        "unit": UNIT_AMPERE_HOUR,\n        "category": "battery",\n    }'
        }
    ],
    
    # NETWORK.PY - Add dBm units to signal strength sensors
    "metrics/common/network.py": [
        {
            "search": r'"m\.net\.mdm\.sq":\s*{\s*"name":\s*"GSM Signal Quality",\s*"description":\s*"GSM signal quality",\s*"icon":\s*"mdi:signal",\s*"device_class":\s*SensorDeviceClass\.SIGNAL_STRENGTH,\s*"state_class":\s*SensorStateClass\.MEASUREMENT,(?:\s*"unit":\s*"[^"]*",)?\s*"category":\s*"network",\s*}',
            "replace": '"m.net.mdm.sq": {\n        "name": "GSM Signal Quality",\n        "description": "GSM signal quality",\n        "icon": "mdi:signal",\n        "device_class": SensorDeviceClass.SIGNAL_STRENGTH,\n        "state_class": SensorStateClass.MEASUREMENT,\n        "unit": "dBm",\n        "category": "network",\n    }'
        },
        {
            "search": r'"m\.net\.sq":\s*{\s*"name":\s*"Network Signal Quality",\s*"description":\s*"Network signal quality",\s*"icon":\s*"mdi:signal",\s*"device_class":\s*SensorDeviceClass\.SIGNAL_STRENGTH,\s*"state_class":\s*SensorStateClass\.MEASUREMENT,(?:\s*"unit":\s*"[^"]*",)?\s*"category":\s*"network",\s*}',
            "replace": '"m.net.sq": {\n        "name": "Network Signal Quality",\n        "description": "Network signal quality",\n        "icon": "mdi:signal",\n        "device_class": SensorDeviceClass.SIGNAL_STRENGTH,\n        "state_class": SensorStateClass.MEASUREMENT,\n        "unit": "dBm",\n        "category": "network",\n    }'
        },
        {
            "search": r'"m\.net\.wifi\.sq":\s*{\s*"name":\s*"WiFi Signal Quality",\s*"description":\s*"WiFi signal quality",\s*"icon":\s*"mdi:wifi",\s*"device_class":\s*SensorDeviceClass\.SIGNAL_STRENGTH,\s*"state_class":\s*SensorStateClass\.MEASUREMENT,(?:\s*"unit":\s*"[^"]*",)?\s*"category":\s*"network",\s*}',
            "replace": '"m.net.wifi.sq": {\n        "name": "WiFi Signal Quality",\n        "description": "WiFi signal quality",\n        "icon": "mdi:wifi",\n        "device_class": SensorDeviceClass.SIGNAL_STRENGTH,\n        "state_class": SensorStateClass.MEASUREMENT,\n        "unit": "dBm",\n        "category": "network",\n    }'
        }
    ],
    
    # PATTERNS.PY - Update signal pattern
    "metrics/patterns.py": [
        {
            "search": r'"signal":\s*{\s*"name":\s*"Signal Strength",\s*"icon":\s*"mdi:signal",\s*"device_class":\s*SensorDeviceClass\.SIGNAL_STRENGTH,\s*"state_class":\s*SensorStateClass\.MEASUREMENT,(?:\s*"unit":\s*"[^"]*",)?\s*"category":\s*"network",\s*"entity_category":\s*EntityCategory\.DIAGNOSTIC,\s*}',
            "replace": '"signal": {\n        "name": "Signal Strength",\n        "icon": "mdi:signal",\n        "device_class": SensorDeviceClass.SIGNAL_STRENGTH,\n        "state_class": SensorStateClass.MEASUREMENT,\n        "unit": "dBm",\n        "category": "network",\n        "entity_category": EntityCategory.DIAGNOSTIC,\n    }'
        }
    ],
    
    # PARSERS.PY - Fix timestamp handling
    "sensor/parsers.py": [
        {
            "search": r"def parse_value\(value: Any, device_class: Optional\[Any\] = None, state_class: Optional\[Any\] = None,\s*is_cell_sensor: bool = False\) -> Any:\s*\"\"\"Parse the value from the payload\.\"\"\"\s*# Handle timestamp device class specifically\s*if device_class == SensorDeviceClass\.TIMESTAMP and isinstance\(value, str\):\s*try:\s*# Try Home Assistant's built-in datetime parser first\s*parsed = dt_util\.parse_datetime\(value\)\s*if parsed:\s*return parsed\s*# For OVMS timestamp format, extract just the datetime part\s*import datetime\s*import re\s*# Match format \"2025-03-25 17:42:57 TIMEZONE\" and extract datetime part\s*match = re\.match\(r'\(\\\d{4}-\\\d{2}-\\\d{2} \\\d{2}:\\\d{2}:\\\d{2}\)', value\)\s*if match:\s*dt_str = match\.group\(1\)\s*# Create a datetime object without timezone info\s*dt_obj = datetime\.datetime\.strptime\(dt_str, '%Y-%m-%d %H:%M:%S'\)\s*# Home Assistant requires tzinfo, but we'll use local time zone\s*return dt_util\.as_local\(dt_obj\)\s*# Return current time if we can't parse it instead of failing\s*return dt_util\.now\(\)\s*except Exception:\s*# Return current time on parse failure instead of None\s*return dt_util\.now\(\)",
            "replace": '''def parse_value(value: Any, device_class: Optional[Any] = None, state_class: Optional[Any] = None,
                is_cell_sensor: bool = False) -> Any:
    """Parse the value from the payload."""
    # Handle timestamp device class specifically
    if device_class == SensorDeviceClass.TIMESTAMP:
        try:
            # If already a datetime object, ensure it has tzinfo
            if hasattr(value, 'tzinfo'):
                if value.tzinfo is None:
                    return dt_util.as_local(value)
                return value
                
            # If it's a string, parse it to datetime
            if isinstance(value, str):
                # Try Home Assistant's built-in datetime parser first
                parsed = dt_util.parse_datetime(value)
                if parsed:
                    return parsed

                # Try parsing ISO format directly
                try:
                    import datetime
                    dt_obj = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
                    if dt_obj.tzinfo is None:
                        return dt_util.as_local(dt_obj)
                    return dt_obj
                except (ValueError, AttributeError):
                    pass

                # For OVMS timestamp format, extract just the datetime part
                import re
                # Match format "2025-03-25 17:42:57 TIMEZONE" and extract datetime part
                match = re.match(r'(\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2})', value)
                if match:
                    dt_str = match.group(1)
                    # Create a datetime object without timezone info
                    dt_obj = datetime.datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
                    # Add timezone
                    return dt_util.as_local(dt_obj)

            # Return current time if we can't parse it
            return dt_util.now()
        except Exception as ex:
            _LOGGER.exception("Error parsing timestamp: %s", ex)
            # Return current time on parse failure
            return dt_util.now()'''
        }
    ]
}

def create_backup(filepath):
    """Create a backup of the original file."""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    
    # Generate backup filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.basename(filepath)
    backup_filepath = os.path.join(BACKUP_DIR, f"{filename}.{timestamp}.bak")
    
    # Copy the file
    shutil.copy2(filepath, backup_filepath)
    return backup_filepath

def apply_patch(filepath, patch_info):
    """Apply a patch to a file."""
    # Create backup
    backup_file = create_backup(filepath)
    
    # Read file content
    with open(filepath, 'r', encoding='utf-8') as file:
        content = file.read()
    
    # Apply patch
    search_pattern = patch_info['search']
    replacement = patch_info['replace']
    
    # Use regex to make the replacement
    try:
        new_content = re.sub(search_pattern, replacement, content, flags=re.DOTALL)
        
        # Check if the content was actually changed
        if new_content == content:
            print(f"  - No changes applied (pattern not found)")
            return False
        
        # Write the modified content back to the file
        with open(filepath, 'w', encoding='utf-8') as file:
            file.write(new_content)
        
        return True
    except re.error as e:
        print(f"  - Error applying patch: {e}")
        return False

def main():
    """Main function to run the script."""
    print("OVMS Integration Fix Script")
    print("==========================")
    
    # Check if we're in the correct directory
    if not os.path.exists(OVMS_DIR):
        print(f"Error: OVMS directory not found at {OVMS_DIR}")
        print("Please run this script from your Home Assistant config directory.")
        sys.exit(1)
    
    # Create backup directory
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        print(f"Created backup directory: {BACKUP_DIR}")
    
    # Apply patches
    for rel_path, patches in FILES_TO_MODIFY.items():
        filepath = os.path.join(OVMS_DIR, rel_path)
        
        if not os.path.exists(filepath):
            print(f"Warning: File not found: {filepath}")
            continue
        
        print(f"Processing {rel_path}:")
        
        for i, patch in enumerate(patches, 1):
            print(f"  Applying patch {i}/{len(patches)}...")
            success = apply_patch(filepath, patch)
            if success:
                print(f"  - Patch applied successfully")
            
    print("\nAll patches applied. Please restart Home Assistant to apply the changes.")
    print(f"Backups of the original files were saved to {BACKUP_DIR}")

if __name__ == "__main__":
    main()
