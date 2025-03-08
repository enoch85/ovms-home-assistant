# OVMS Home Assistant
![logo](/assets/logo.png)

The [Open Vehicle Monitoring System (OVMS)](https://www.openvehicles.com/) integration for Home Assistant. Connect your electric vehicle with Home Assistant via MQTT, automatically creating sensors for all vehicle metrics.

## Overview

The OVMS integration discovers and creates Home Assistant entities from MQTT topics published by your OVMS module. The integration automatically:

- Identifies vehicle data and creates appropriate entity types (sensors, binary sensors, device trackers)
- Categorizes entities by data type (battery, climate, location, etc.)
- Maintains entity state based on real-time MQTT updates
- Provides services to send commands to your vehicle

![Entity Overview](/assets/entity-overview.svg)

## Features

- **Automatic Discovery**: Detects all metrics published by your OVMS module
- **Entity Creation**: Creates appropriate Home Assistant entities based on data type
- **Smart Categorization**: Organizes entities into logical groups
- **Real-time Updates**: Entities update as new data is published
- **Command Interface**: Send commands to your vehicle through services
- **Vehicle Status**: Track online/offline status of your vehicle
- **Secure Communication**: Supports TLS/SSL connections to MQTT brokers

## Requirements

- Home Assistant (2023.10.0 or newer)
- MQTT integration configured in Home Assistant
- OVMS module publishing to the same MQTT broker
- OVMS firmware 3.3.001 or newer recommended

## Installation

### HACS Installation (Recommended)

1. Add this repository to HACS:
   - Go to HACS → Integrations → ⋮ (menu) → Custom repositories
   - Enter repository URL: `https://github.com/enoch85/ovms-home-assistant`
   - Category: Integration
   - Click "Add"

2. Install the integration:
   - Go to HACS → Integrations → "OVMS Home Assistant"
   - Click "Download"
   - Restart Home Assistant

### Manual Installation

1. Download the repository as a ZIP file and extract it
2. Copy the `custom_components/ovms` folder to your Home Assistant's `custom_components` directory
3. Restart Home Assistant

## MQTT Broker Configuration

Before using this integration, you need to configure your MQTT broker with the correct permissions:

### Required ACL (Access Control List) Permissions

The OVMS integration needs the following MQTT permissions:

**Subscribe Permissions:**
- `ovms/#` - For all OVMS topics (replace `ovms` with your chosen prefix if different)
- `homeassistant/#` - For testing connection during setup

**Publish Permissions:**
- `ovms/+/+/client/rr/command/#` - For sending commands to the OVMS module
- `ovms/+/+/status` - For publishing online/offline status

If you're using a broker with restrictive ACLs (like Mosquitto, EMQX, etc.), ensure your MQTT user has these permissions.

### Example Mosquitto ACL Configuration:

```
user ovms_user
topic read ovms/#
topic write ovms/+/+/client/rr/command/#
topic write ovms/+/+/status
```

## OVMS Configuration

Configure your OVMS module to publish data to your MQTT broker:

1. In the OVMS web UI, go to Config → Server V3 (MQTT)
2. Configure the following settings:
   - Server: Your MQTT broker address
   - Port: 1883 (standard) or 8883 (TLS/SSL)
   - Username/Password: If required by your broker
   - Topic Prefix: `ovms` (default, can be customized)
   - Enable Auto-Start: YES

![OVMS MQTT Configuration](/assets/ovms-mqtt-config.svg)

## Home Assistant Configuration

### Basic Setup

1. Go to Settings → Devices & Services → Add Integration
2. Search for "OVMS" and select it
3. Enter the MQTT broker details:
   - MQTT Broker: Your broker address
   - Port: Choose between standard (1883) or TLS/SSL (8883)
   - Username/Password: If required by your broker
4. Configure topic structure:
   - Topic Prefix: Should match your OVMS setting (default: `ovms`)
   - MQTT Username: Username that OVMS uses in its topics
5. The integration will scan for available OVMS vehicles
6. Select your vehicle ID when prompted

![Setup Flow](/assets/setup-flow.svg)

### Testing Configuration

For testing purposes, you can:

1. Enable debug logging by adding to your `configuration.yaml`:
   ```yaml
   logger:
     default: info
     logs:
       custom_components.ovms: debug
   ```

2. Monitor MQTT messages using an external tool like MQTT Explorer to verify what your OVMS is publishing

3. Check the Home Assistant logs for detailed information about discovered topics and created entities

## Using the Integration

### Available Entities

After setup, entities will be created for your vehicle metrics. These include:

- **Battery**: State of charge, range, power, voltage, etc.
- **Climate**: Temperature readings from various vehicle sensors
- **Location**: GPS position of the vehicle
- **Status**: Connection state, operational parameters
- **Vehicle-specific**: Other metrics specific to your vehicle model

Entities are grouped under a device representing your vehicle, identified by the vehicle ID.

### Services

The integration provides several services to interact with your vehicle:

#### `ovms.send_command`
Send any command to the OVMS module.

```yaml
service: ovms.send_command
data:
  vehicle_id: your_vehicle_id
  command: stat
  parameters: range
```

Could be done as a button in HA:

```yaml
show_name: true
show_icon: true
type: button
tap_action:
  action: perform-action
  perform_action: ovms.send_command
  target: {}
  data:
    timeout: 10
    vehicle_id: REG123
    command: server v3 update all
entity: input_button.ovms_update_all
hold_action:
  action: none
name: "REG123: update all"
```

#### `ovms.set_feature`
Set an OVMS configuration feature.

```yaml
service: ovms.set_feature
data:
  vehicle_id: your_vehicle_id
  feature: feature_name
  value: feature_value
```

#### `ovms.control_climate`
Control the vehicle's climate system.

```yaml
service: ovms.control_climate
data:
  vehicle_id: your_vehicle_id
  temperature: 21.5
  hvac_mode: heat
  duration: 30
```

#### `ovms.control_charging`
Control the vehicle's charging functions.

```yaml
service: ovms.control_charging
data:
  vehicle_id: your_vehicle_id
  action: start
  mode: range
  limit: 80
```

## Technical Details

### Topic Structure

The integration supports these MQTT topic structures:

- Default: `ovms/username/vehicle_id/metric/...`
- Alternative: `ovms/client/vehicle_id/...`
- Simple: `ovms/vehicle_id/...`
- Custom: Define your own structure with placeholders

### Communication Flow

1. OVMS module publishes metrics to MQTT broker
2. Integration subscribes to all topics under the configured prefix
3. Received messages are parsed to determine entity type and attributes
4. Entities are created or updated based on the incoming data
5. Commands are sent via MQTT and responses are tracked

### Entity Classification

The integration uses pattern matching to determine entity types:

- Metrics with temperature data become temperature sensors
- Location data becomes device trackers
- Binary states (on/off, connected/disconnected) become binary sensors
- Numeric values become standard sensors

### Command Protocol

Commands use a request-response pattern:
1. Command is published to: `{prefix}/{username}/{vehicle_id}/client/rr/command/{command_id}`
2. Response is received on: `{prefix}/{username}/{vehicle_id}/client/rr/response/{command_id}`
3. Unique command IDs ensure responses are matched to requests

You can for example use the developer tool in Home Assistant to update all the metrics at once with this command:

![send update all](/assets/send_update_all.png)

## Troubleshooting

*Warning! The debug output is substancial. It may fill your disk if you are not careful, don't leave it turned on.*

### No Entities Created

1. Check if your OVMS module is publishing to the MQTT broker
2. Verify the topic structure matches what's configured in the integration
3. Enable debug logging and check for errors in the Home Assistant logs
4. Ensure your MQTT broker allows wildcard subscriptions (#)
5. Verify ACL permissions in your MQTT broker for the topics listed above

### Connection Issues

1. Verify MQTT broker credentials are correct
2. Check if TLS/SSL settings match between OVMS, Home Assistant, and the broker
3. Test connection using an external MQTT client
4. Check firewall rules if using different networks

### Command Failures

1. Ensure the OVMS module is online
2. Check if the command syntax is correct for your vehicle
3. Verify MQTT QoS settings allow reliable message delivery
4. Look for command responses in the logs

## Advanced Usage

### Custom Topic Structure

If your OVMS uses a non-standard topic structure, you can define a custom pattern during setup using these placeholders:

- `{prefix}`: The base MQTT topic prefix
- `{mqtt_username}`: The username portion of the topic
- `{vehicle_id}`: The vehicle identifier

### Dashboard Example

Here's an example card configuration for a vehicle dashboard:

```yaml
type: vertical-stack
cards:
  - type: entities
    title: Vehicle Status
    entities:
      - entity: sensor.ovms_v_b_soc
        name: Battery
      - entity: sensor.ovms_v_b_range_est
        name: Range
      - entity: sensor.ovms_v_c_charging
        name: Charging
      - entity: sensor.ovms_v_p_odometer
        name: Odometer
  - type: map
    entities:
      - entity: device_tracker.ovms_location
```

## FAQ

**Q: Can I use multiple vehicles with this integration?**  
A: Yes, you can set up multiple instances of the integration, one for each vehicle.

**Q: Does this work with all OVMS-supported vehicles?**  
A: Yes, the integration is vehicle-agnostic and works with any vehicle supported by OVMS.

**Q: Can I use this without internet access?**  
A: Yes, as long as your OVMS module, MQTT broker, and Home Assistant can communicate on the same network.

**Q: How frequent are the updates?**  
A: Updates happen in real-time as the OVMS module publishes new data, typically every few seconds while the vehicle is active.

## License

MIT License - see LICENSE file

---

*This integration is not officially affiliated with the Open Vehicles project.*
