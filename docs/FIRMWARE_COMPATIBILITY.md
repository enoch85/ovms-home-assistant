# OVMS Firmware Compatibility

This document describes firmware version requirements for integration features.

## Minimum Requirements

- **3.3.001**: Basic MQTT publishing and command support
- **3.3.003**: GPS signal quality metric (`v.p.gpssq`)
- **3.3.004**: Improved MQTT stability and reliability  
- **3.3.005**: Current stable release, 12V aux battery monitor commands
- **Edge** (unreleased): On-demand metric requests, climate scheduling, TPMS mapping

## Feature Compatibility

| Feature | Min Version | Notes |
|---------|-------------|-------|
| Basic sensors | 3.3.001 | All standard vehicle metrics |
| Commands (`ovms.send_command`) | 3.3.001 | Raw command interface |
| GPS signal quality (`v.p.gpssq`) | 3.3.003 | 0-100% quality metric |
| 12V Aux monitor (`ovms.aux_monitor`) | 3.3.005 | `vehicle aux monitor` commands |
| Fast discovery (10s) | Edge | On-demand metric requests |
| Climate scheduling (`ovms.climate_schedule`) | Edge | `climatecontrol schedule` commands |
| TPMS mapping (`ovms.tpms_map`) | Edge | `tpms map` commands |

## Service Compatibility Details

### Services Available on 3.3.005

- `ovms.send_command` - Send any raw command
- `ovms.set_feature` - Set vehicle features
- `ovms.control_climate` - Basic climate on/off
- `ovms.control_charging` - Charging start/stop
- `ovms.homelink` - Homelink buttons
- `ovms.aux_monitor` - 12V battery monitoring

### Services Requiring Edge Firmware

- `ovms.climate_schedule` - Schedule climate preconditioning
- `ovms.tpms_map` - TPMS sensor wheel mapping

**Note**: Using edge-only services on 3.3.005 will return an error like:
`Error: Unrecognised command: schedule` or `Error: Unrecognised command: map`

## Fallback Behavior

The integration automatically detects firmware capabilities:

1. **Discovery**: Tries on-demand metric request first (edge firmware), falls back to passive 60s discovery on older firmware
2. **GPS accuracy**: Uses `v.p.gpssq` when available (3.3.003+)
3. **Edge services**: Return clear error messages on older firmware

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

## Edge Firmware

To get the latest features before they're in a stable release, you can use edge firmware:

1. In OVMS shell: `ota boot edge`
2. Or via web: Config → Firmware → Select "edge" partition

**Warning**: Edge firmware may be less stable than official releases.

## Changelog Reference

Full OVMS firmware changelog:
https://raw.githubusercontent.com/openvehicles/Open-Vehicle-Monitoring-System-3/refs/heads/master/vehicle/OVMS.V3/changes.txt
