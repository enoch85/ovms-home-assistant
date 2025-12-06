# OVMS Firmware Compatibility

This document describes firmware version requirements for integration features.

## Minimum Requirements

- **3.3.001**: Basic MQTT publishing and command support
- **3.3.004**: Improved MQTT stability and reliability  
- **3.3.005**: Current stable release
- **Edge**: On-demand metric requests, GPS signal quality metric (v.p.gpssq)

## Feature Compatibility

| Feature | Min Version | Notes |
|---------|-------------|-------|
| Basic sensors | 3.3.001 | All standard vehicle metrics |
| Commands | 3.3.001 | `ovms.send_command` service |
| Fast discovery | Edge | 10s vs 60s setup time |
| GPS accuracy (v.p.gpssq) | Edge | 0-100% quality metric |
| Climate scheduling | 3.3.003 | `climatecontrol schedule` commands |

## Fallback Behavior

The integration automatically detects firmware capabilities:

1. **Discovery**: Tries on-demand metric request first (edge firmware), falls back to passive discovery
2. **GPS accuracy**: Uses `v.p.gpssq` when available
3. **All features**: Gracefully degrade on stable firmware - no errors, just reduced functionality

## Checking Your Firmware Version

In OVMS shell:
```
OVMS# ota status
```

Or via web interface: Config → Firmware → Version

## Recommended Configuration

For optimal performance with this integration:
```
# Enable MQTT server v3
config set server.v3 server your-mqtt-broker.com

# Optional: Filter metrics to reduce traffic
config set server.v3 metrics.include "v.b.*,v.c.*,v.p.*,v.e.*,v.d.*"
```

## Changelog Reference

Full OVMS firmware changelog:
https://raw.githubusercontent.com/openvehicles/Open-Vehicle-Monitoring-System-3/refs/heads/master/vehicle/OVMS.V3/changes.txt
