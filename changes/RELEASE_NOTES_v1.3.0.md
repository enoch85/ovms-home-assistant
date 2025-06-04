# OVMS Home Assistant Integration v1.3.0 Release Notes

## ⚠️ BREAKING CHANGES - IMPORTANT UPGRADE NOTICE

This release contains significant improvements to entity naming and identification that will affect existing installations. **Please read this entire notice before upgrading.**

### What Changed

We've completely overhauled the entity naming system to provide:
- **Better collision avoidance** with 12-character unique identifiers (vs previous 8-character)
- **Clearer entity differentiation** between sensors and binary sensors
- **Improved name consistency** with enhanced cleaning and formatting
- **Vehicle-specific naming** for better user experience

### Impact on Your Installation

**After upgrading, you will see:**
- ✅ New entities with improved names appearing in Home Assistant
- ❌ Old entities becoming "unavailable" (showing as unavailable in entity registry)
- ⚠️ Dashboards referencing old entity IDs will need updates
- ⚠️ Automations using old entity IDs will need updates

### Examples of Changes

**Smart ForTwo Battery Voltage:**
- **Before:** `sensor.ovms_mycar_sensor_battery_voltage_a1b2c3d4`
- **After:** `sensor.ovms_mycar_sensor_battery_voltage_12v_a1b2c3d4e5f6`

**Nissan Leaf State of Charge:**
- **Before:** `sensor.ovms_mycar_sensor_battery_soc_x9y8z7w6`
- **After:** `sensor.ovms_mycar_sensor_battery_soc_p9q8r7s6t5u4`

**Binary Sensors (NEW - now properly differentiated):**
- **Before:** `sensor.ovms_mycar_sensor_charging_pilot_m5n4o3p2`
- **After:** `binary_sensor.ovms_mycar_binary_sensor_charging_pilot_present_k8j7i6h5g4f3`

### Migration Steps

1. **Before Upgrading:**
   - Take screenshots of important dashboards
   - Note down any automations using OVMS entities
   - Consider exporting your Home Assistant configuration

2. **After Upgrading:**
   - Go to **Settings > Devices & Services > Entities**
   - Filter by "ovms" to see both old (unavailable) and new entities
   - Update your dashboards to use the new entity IDs
   - Update your automations to reference the new entity IDs
   - Remove old unavailable entities from the entity registry (optional cleanup)

3. **Finding New Entity Names:**
   - New entities will appear with the same friendly names (e.g., "Smart ForTwo Battery Voltage")
   - Use the entity search in dashboards to find entities by their friendly names
   - Check the Developer Tools > States tab to see all current entity IDs

### New Features & Improvements

- 🚗 **Vehicle-Specific Naming**: Smart ForTwo, Nissan Leaf, VW eUP!, MG ZS-EV, and Renault Twizy now have tailored entity names
- 🎯 **Better Categorization**: Location sensors are now properly categorized (fixes GPS-related entities)
- 🔧 **Enhanced Reliability**: Improved unique ID generation prevents entity conflicts
- 📱 **Binary Sensor Support**: Proper differentiation between regular sensors and binary sensors
- 🧹 **Cleaner Names**: Consistent naming format with improved character handling
### Technical Details

The unique ID format has changed from:
```
{vehicle_id}_{category}_{name}_{8-char-hash}
```
to:
```
{vehicle_id}_{entity_type}_{category}_{clean_name}_{12-char-hash}
```

This ensures better collision avoidance and clearer entity identification.

### Need Help?

If you encounter issues during migration:
1. Check the Home Assistant logs for any OVMS-related errors
2. Verify your MQTT connection is still working
3. Ensure your OVMS vehicle is publishing data correctly
4. Consider restarting Home Assistant after the upgrade

### Support

For questions or issues related to this release:
- Open an issue on the project GitHub repository
- Include your Home Assistant version and OVMS integration version
- Provide relevant log entries if experiencing problems

---

**We apologize for the inconvenience of these breaking changes, but they lay the foundation for a much more reliable and user-friendly experience going forward.**
