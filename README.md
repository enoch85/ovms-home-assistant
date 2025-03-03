# OVMS MQTT Integration for Home Assistant

This integration connects your Open Vehicle Monitoring System (OVMS) with Home Assistant via MQTT, automatically creating sensors for all vehicle metrics.

## WIP

The current implementation does *not* work. If you want to test it you need to manually move [this folder](https://github.com/enoch85/ovms-mqtt-integration/tree/main/custom_components/ovms_mqtt) to your Home Assistant and activate the integration.

In its current state, it installs fine, and produces no errors, but [no enteties are produced](https://github.com/enoch85/ovms-mqtt-integration/issues/12).

## First look

![image](https://github.com/user-attachments/assets/4494a2f9-4534-4e3a-8486-51100b6f1bb3)

## Features

- Automatic discovery of OVMS vehicles and metrics
- CAutomatically create sensors for battery state, location, charging status, soc and more
- Organizes sensors by vehicle_id
- Handles notifications and client commands
- User-friendly entity naming

## Requirements

- Home Assistant (2023.10.0 or newer)
- MQTT integration configured in Home Assistant
- OVMS module publishing to the same MQTT broker

## Installation

### HACS Installation

1. Add this repository to HACS:
   - Go to HACS → Integrations → ⋮ (menu) → Custom repositories
   - Enter repository URL: `https://github.com/enoch85/ovms-mqtt-integration`
   - Category: Integration
   - Click "Add"

2. Install the integration:
   - Go to HACS → Integrations → "OVMS MQTT Integration"
   - Click "Download"
   - Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/ovms_mqtt` folder to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

## Configuration

1. Make sure your OVMS module is configured to publish to your MQTT broker
   - In OVMS web UI: Config → Server V3 (MQTT)
   - Set server address, credentials, and topic prefix (default: `ovms`)

2. Add the integration in Home Assistant:
   - Settings → Devices & Services → Add Integration
   - Search for "OVMS MQTT Integration"
   - Enter your MQTT broker details:
     - Broker address
     - Port (1883 for unsecured, 8883 for SSL)
     - Username/password
     - Topic prefix (must match OVMS config)

## Testing

1. Check Home Assistant logs for successful connection messages
2. Verify entity creation:
   - Go to Settings → Devices & Services → Entities
   - Filter by "OVMS" to see discovered sensors
   - Entities should appear within 1-2 minutes of OVMS publishing data

3. Troubleshooting:
   - Enable debug logging by adding to configuration.yaml:
     ```yaml
     logger:
       default: info
       logs:
         custom_components.ovms_mqtt: debug
     ```
   - Use an MQTT client (like MQTT Explorer) to verify topics are being published
   - Manually publish a test message to `ovms/test` to check MQTT connectivity

## Topic Structure

The integration processes these MQTT topics:
- `ovms/username/vehicle_id/metric/...` - Vehicle metrics
- `ovms/username/vehicle_id/notify/...` - Notifications
- `ovms/username/vehicle_id/client/...` - Client commands/responses

Example metrics include:
- `v/b/soc` - Battery state of charge
- `v/p/latitude` and `v/p/longitude` - Location
- `v/b/range/est` - Estimated range
- `v/c/limit/soc` - Charge limit
- `v/b/12v/voltage` - 12V battery voltage

## License

MIT License - see LICENSE file
