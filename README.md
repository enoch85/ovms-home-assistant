# OVMS Home Assistant
![logo](/assets/logo.png)

The [Open Vehicle Monitoring System (OVMS)](https://www.openvehicles.com/) integration for Home Assistant. Connect your electric vehicle with Home Assistant via MQTT, automatically creating sensors for all vehicle metrics.

## Overview

[![ovms-home-assistant_downloads](https://img.shields.io/github/downloads/enoch85/ovms-home-assistant/total)](https://github.com/enoch85/ovms-home-assistant)
[![ovms-home-assistant_downloads](https://img.shields.io/github/downloads/enoch85/ovms-home-assistant/latest/total)](https://github.com/enoch85/ovms-home-assistant)

The OVMS integration discovers and creates Home Assistant entities from MQTT topics published by your OVMS module. The integration automatically:

- Identifies vehicle data and creates appropriate entity types (sensors, binary sensors, device trackers, switches)
- Categorizes entities by data type (battery, climate, location, etc.)
- Maintains entity state based on real-time MQTT updates
- Processes data for comprehensive metrics including statistics
- Provides services to send commands to your vehicle

## Features

- **Automatic Discovery**: Detects all metrics published by your OVMS module without manual configuration
- **Entity Creation**: Creates appropriate Home Assistant entities based on data type with intelligent state parsing
- **Smart Categorization**: Organizes entities into logical groups (battery, climate, location, etc.)
- **Real-time Updates**: Entities update as new data is published through MQTT
- **Command Interface**: Send commands to your vehicle through services with proper rate limiting
- **Vehicle Status**: Track online/offline status of your vehicle automatically
- **Secure Communication**: Supports TLS/SSL connections to MQTT brokers with certificate verification
- **Vehicle-Specific Metrics**: Special support for VW e-UP! with additional vehicle models planned
- **Diagnostics Support**: Provides detailed diagnostics for troubleshooting
- **Flexible Topic Structure**: Supports various MQTT topic structures including custom formats
- **Multi-language Support**: Includes translations for English, German, and Swedish
- **GPS Tracking**: Advanced location tracking with accuracy estimation from signal quality
- **Cell-level Battery Data**: Processes and displays individual cell data with statistical analysis
- **Command Rate Limiting**: Prevents overwhelming the vehicle with too many commands

## Technical Quality

- **Code Structure**: Well-organized codebase with proper separation of concerns
- **Error Handling**: Comprehensive error handling with detailed logging
- **Type Hints**: Full Python type hinting for better code maintainability
- **Security**: SSL/TLS support, credential protection, and input validation
- **Standards Compliance**: Follows Home Assistant development guidelines
- **Performance**: Efficient MQTT message processing with minimal overhead
- **Reliability**: Connection recovery mechanisms with backoff strategy
- **Testing**: Automated validations via HACS and Hassfest
- **Maintenance**: Structured release process with version control

## Requirements

- Home Assistant (2025.2.5 or newer) according to HACS specification
- MQTT integration configured in Home Assistant
- OVMS module publishing to the same MQTT broker
- OVMS firmware 3.3.001 or newer recommended
- Python package: paho-mqtt>=1.6.1 (installed automatically)

## Screenshots
![1](/assets/screenshot-overview1.png)

*Integration overview 1*

![2](/assets/screenshot-overview2.png)

*Integration overview 2*

![3](/assets/screenshot-overview3.png)

*All topics with a lot of metrics are stored in attributes instead, where the average and median are calculated and presented*

## Installation

### HACS Installation (Recommended)

1. In Home Assistant go to HACS -> Integrations. Click on "+ Explore & Download Repositories" and search for "OVMS Home Assistant".

   [![OPEN HACS REPOSITORY ON](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=enoch85&repository=ovms-home-assistant&category=integration)

2. In Home Assistant go to Settings -> Devices & Services -> Integrations. Click on "+ Add integration" and search for "OVMS".

   [![ADD INTEGRATION TO](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=ovms)

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
   - Port: 8883 (TLS/SSL, standard) or 1883 (unencrypted)
   - Username/Password: If required by your broker
   - Topic Prefix: `ovms` (default, can be customized)
   - Enable Auto-Start: YES

![OVMS GUI](/assets/screenshot-ovms-gui.png)

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
  timeout: 10  # Optional timeout in seconds
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

![screenshot-command](/assets/screenshot-command.png)

*Example of how a command button could look like in the Lovelace UI*

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
  hvac_mode: heat  # Options: off, heat, cool, auto
  duration: 30  # Duration in minutes
```

#### `ovms.control_charging`
Control the vehicle's charging functions.

```yaml
service: ovms.control_charging
data:
  vehicle_id: your_vehicle_id
  action: start  # Options: start, stop, status
  mode: range  # Options: standard, storage, range, performance
  limit: 80  # Percentage limit for charging
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

The integration uses pattern matching and metric definitions to determine entity types:

- Metrics with temperature data become temperature sensors
- Location data becomes device trackers
- Binary states (on/off, connected/disconnected) become binary sensors
- Numeric values become standard sensors
- Array data (like cell voltages) is processed with statistical analysis

### Command Protocol

Commands use a request-response pattern:
1. Command is published to: `{prefix}/{username}/{vehicle_id}/client/rr/command/{command_id}`
2. Response is received on: `{prefix}/{username}/{vehicle_id}/client/rr/response/{command_id}`
3. Unique command IDs ensure responses are matched to requests

You can for example use the developer tool in Home Assistant to update all the metrics at once with this command:

![send update all](/assets/send_update_all.png)

### Data Processing

The integration includes sophisticated data processing:
- Auto-detection of data types and units
- Extraction of statistics from array data (min, max, average, median)
- Conversion between different units based on user preferences
- JSON payload parsing for complex data structures
- GPS accuracy calculation from quality metrics

## Security Features

- **TLS/SSL Support**: Secure encrypted connections to MQTT broker
- **Certificate Verification**: Option to verify SSL certificates (enabled by default)
- **Rate Limiting**: Command limiting to prevent overwhelming the vehicle (5 per minute by default)
- **Input Validation**: Comprehensive validation of all inputs
- **MQTT ACL**: Detailed guidance for restrictive MQTT permissions

## Troubleshooting

*Warning! The debug output is substantial. It may fill your disk if you are not careful, don't leave it turned on.*

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

## Code Quality and Maintenance

The OVMS integration follows these development principles:

- **Modular Architecture**: Separation of concerns with dedicated modules for specific functions
- **Comprehensive Logging**: Detailed logging for troubleshooting at various levels
- **Consistent Formatting**: Code formatted with Black and checked with Pylint
- **Automated Testing**: CI/CD pipeline with GitHub Actions for validation
- **Release Management**: Structured release process with semantic versioning
- **Documentation**: Extensive inline documentation and comments

This integration undergoes regular validation through:
- HACS compatibility checking
- Hassfest validation for Home Assistant standards
- Python code validation and linting
- Version checking and dependency management

## FAQ

**Q: Can I use multiple vehicles with this integration?**  
A: Yes, you can set up multiple instances of the integration, one for each vehicle.

**Q: Does this work with all OVMS-supported vehicles?**  
A: Yes, the integration is vehicle-agnostic and works with any vehicle supported by OVMS. Vehicle-specific enhancements are provided for some models like VW e-UP!

**Q: Can I use this without internet access?**  
A: Yes, as long as your OVMS module, MQTT broker, and Home Assistant can communicate on the same network.

**Q: How frequent are the updates?**  
A: Updates happen in real-time as the OVMS module publishes new data, typically every few seconds while the vehicle is active.

**Q: How does the integration handle connectivity issues?**  
A: The integration includes automatic reconnection with exponential backoff, online/offline status tracking, and will resume normal operation when connection is restored.

**Q: Is my data secure?**  
A: Yes, the integration supports TLS/SSL encryption for MQTT connections and follows secure coding practices for handling sensitive data.

## Contributing

Contributions to the OVMS Home Assistant integration are welcome! Whether it's bug reports, feature requests, documentation improvements, or code contributions.

To contribute:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

Please ensure your code follows the existing style conventions and includes appropriate tests and documentation.

## License

MIT License - see LICENSE file

---

*This integration is not officially affiliated with the Open Vehicles project, yet.*
