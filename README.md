# OVMS Home Assistant
![logo](/assets/logo.png)

The [Open Vehicle Monitoring System (OVMS)](https://www.openvehicles.com/) integration for Home Assistant. Connect your electric vehicle with Home Assistant via MQTT, automatically creating sensors for all vehicle metrics.

## Overview

<!--
[![ovms-home-assistant_downloads](https://img.shields.io/github/downloads/enoch85/ovms-home-assistant/total)](https://github.com/enoch85/ovms-home-assistant)
[![ovms-home-assistant_downloads](https://img.shields.io/github/downloads/enoch85/ovms-home-assistant/latest/total)](https://github.com/enoch85/ovms-home-assistant)
-->

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
- **Vehicle-Specific Metrics**: Special support for VW e-UP!, Smart ForTwo, Nissan Leaf, and MG ZS-EV - with additional vehicle models planned
- **Diagnostics Support**: Provides detailed diagnostics for troubleshooting
- **Flexible Topic Structure**: Supports various MQTT topic structures including custom formats
- **Multi-language Support**: Includes translations for English, French, German, Spanish, and Swedish
- **GPS Tracking**: Advanced location tracking with accuracy estimation from signal quality
- **Cell-level Battery Data**: Processes and displays individual cell data with statistical analysis
- **Command Rate Limiting**: Prevents overwhelming the vehicle with too many commands
- **Intelligent Attribute Enrichment**: Automatically adds useful derived attributes to entities (battery level categorization, temperature comfort levels, etc.)
- **Advanced Formatting**: Intelligent formatting for duration values (minutes, hours, days) and timestamps
- **Dynamic Topic Discovery**: Sophisticated topic detection even with non-standard username patterns
- **Combined Location Tracking**: Automatically creates unified device tracker from separate latitude/longitude entities

## Technical Quality

- **Code Structure**: Well-organized codebase with proper separation of concerns
- **Error Handling**: Comprehensive error handling with detailed logging
- **Type Hints**: Full Python type hinting for better code maintainability
- **Security**: SSL/TLS support, credential protection, and input validation
- **Standards Compliance**: Follows Home Assistant development guidelines
- **Performance**: Efficient MQTT message processing with minimal overhead
- **Reliability**: Connection recovery mechanisms with exponential backoff strategy
- **Testing**: Automated validations via HACS and Hassfest
- **Maintenance**: Structured release process with version control

## Requirements

- Home Assistant (2025.2.5 or newer) according to HACS specification
- MQTT integration configured in Home Assistant
- OVMS module publishing to the same MQTT broker
- OVMS firmware 3.3.001 or newer recommended (3.3.004+ for optimal performance)
- Python package: paho-mqtt>=1.6.1 (installed automatically)

## Known "Issues" and Solutions

- If you have trouble with certain metrics not appearing, try the `server v3 update all` command. Please see [this section](https://github.com/enoch85/ovms-home-assistant?tab=readme-ov-file#ovmssend_command) for more information. This command will update all of your metrics at once in the OVMS module, and in turn send the updated metrics over to the broker which is then picked up by the integration.
- Some metrics may show as unavailable initially. This is normal until the vehicle provides data for these metrics.
- For best results, ensure your OVMS module firmware is updated to at least version 3.3.004 or higher.


## Screenshots
![1](/assets/screenshot-overview1.png)

*Integration overview 1*

![2](/assets/screenshot-overview2.png)

*Integration overview 2*

## Cell Battery Data Analysis

The integration provides comprehensive analysis of cell-level battery data:

- **Statistical Processing**: Instead of creating dozens of individual sensors for each cell, the integration automatically calculates statistical measures (minimum, maximum, average, median) for cell voltages, temperatures, and health values
- **Attribute-Based Storage**: These statistics are stored as attributes on the main sensor, providing easy access while keeping your entities list clean
- **Cell Deviation Tracking**: The integration tracks and displays voltage and temperature deviations between cells, helping to identify potential battery pack issues
- **Historical Tracking**: Maximum deviation values are tracked over time to help identify battery degradation patterns

![3](/assets/screenshot-overview3.png)

*Example of cell statistics in entity attributes - these values are automatically calculated*

## Data usage

Compared to using the OVMS V2 server, this integration will use more data since it's using the V3 server over MQTT. If you are concerned about data usage, this integration might not be for you. Below are real-life cellular data usage from a car with both V2 and V3 OVMS server activated.

**Specifications of the car in the example:**

- While parked at home: WIFI
- While parked at work: 4G
- Traveled to work: 22 times
- Duration of travel to work: 40 minutes per trip

![data-usage](/assets/screenshot-data-usage.png)
*The grah above are showing the usage over one month.*

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

### Security Best Practices

When setting up your MQTT broker for OVMS:

- **Use Strong Credentials**: Create a dedicated user for OVMS with a strong password
- **Apply Minimal Permissions**: Follow the principle of least privilege with the ACL shown above
- **Enable TLS/SSL**: Use port 8883 with TLS encryption for all connections
- **Certificate Verification**: Enable certificate verification in production environments
- **Network Segregation**: If possible, keep your MQTT broker on a separate network segment

The integration supports secure connections with TLS, proper certificate validation, and username/password authentication to ensure your vehicle data remains protected.

## OVMS Configuration

Configure your OVMS module to publish data to your MQTT broker:

1. In the OVMS web UI, go to Config → Server V3 (MQTT)
2. Configure the following settings:
   - Server: Your MQTT broker address
   - Port:
       - TCP Port: 1883 (mqtt://)
       - WebSocket Port: 8083 (ws://)
       - SSL/TLS Port: 8883 (mqtts://)
       - Secure WebSocket Port: 8084 (wss://)
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
   - Port:
       - TCP Port: 1883 (mqtt://)
       - WebSocket Port: 8083 (ws://) - default
       - SSL/TLS Port: 8883 (mqtts://)
       - Secure WebSocket Port: 8084 (wss://)
   - Username/Password: If required by your broker
4. Configure topic structure:
   - Topic Prefix: Should match your OVMS setting (default: `ovms`)
   - MQTT Username: Username that OVMS uses in its topics
5. The integration will scan for available OVMS vehicles
6. Select your vehicle ID when prompted

![Setup Flow](/assets/setup-flow.svg)

### Advanced Options

After initial setup, additional options can be configured via the integration options:

1. Go to Settings → Devices & Services → OVMS → Configure
2. Configure additional options:
   - **Topic Blacklist**: A comma-separated list of topics to exclude from creating entities (e.g., `.log,battery.log,power.log,gps.log`)
   - **Topic Structure**: Choose or customize your topic structure format
   - **Quality of Service (QoS)**: Choose the MQTT QoS level (0, 1, or 2)

The Topic Blacklist feature is particularly useful to prevent high-frequency log topics from creating hundreds of unwanted entities. The integration comes with default filters for common log topics, but you may need to add additional patterns based on your specific OVMS module and vehicle.

**Common patterns to blacklist:**
- `.log` - Blocks all log topics (matches any topic containing ".log")
- `battery.log` - Blocks battery log specific topics
- `power.log` - Blocks power log specific topics
- `gps.log` - Blocks GPS log specific topics
- `xrt.log` - Blocks Renault Twizy specific log topics

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

### Debugging and Logs

*Warning! The debug output is substantial. It may fill your disk if you are not careful, don't leave it turned on.*

The integration provides several levels of logging:

- **Info Level**: Basic operational information (connections, entity creation)
- **Debug Level**: Detailed information about topic discovery, message processing, and entity creation
- **Warning/Error Levels**: Issues that might need attention

Common log patterns to look for:

- `Topic discovery completed` - Indicates successful MQTT topic scanning
- `Adding sensor/binary_sensor/device_tracker` - Shows entity creation
- `MQTT connection test completed` - Shows broker connection results
- `Command response for...` - Shows command execution results

To interpret logs effectively:
1. Look for error messages indicating connection issues
2. Check for topics being discovered correctly
3. Verify entity creation messages for your expected metrics
4. Watch for command results when testing integration functions

## Using the Integration

### Available Entities

After setup, entities will be created for your vehicle metrics. These include:

- **Battery**: State of charge, range, power, voltage, etc.
- **Climate**: Temperature readings from various vehicle sensors
- **Location**: GPS position of the vehicle
- **Status**: Connection state, operational parameters
- **Vehicle-specific**: Other metrics specific to your vehicle model

Entities are grouped under a device representing your vehicle, identified by the vehicle ID.

### Data Presentation and Formatting

The integration intelligently formats data to enhance usability:

- **Duration Values**: Time values are automatically formatted in the most appropriate units (minutes, hours, days) with both short form (5h 30m) and full text variants available as attributes
- **Timestamps**: Dates and times are displayed in a human-readable format
- **Battery Levels**: Battery entities include a "battery_level" attribute categorizing the state as low/medium/high
- **Temperature Comfort**: Temperature entities include a "temperature_level" attribute (freezing/cold/cool/comfortable/warm/hot)
- **GPS Accuracy**: Location entities automatically include accuracy estimates derived from GPS signal quality

### Version Detection

The integration automatically detects your OVMS module's firmware version and displays it in the device info:

- The version is extracted from the MQTT messages
- Device info is updated in the Home Assistant device registry
- The integration recommends OVMS firmware 3.3.004 or higher for optimal operation

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

#### Common OVMS Commands

Here are some useful OVMS commands you can send through the service:

| Command | Description | Example Parameters |
|---------|-------------|-------------------|
| `stat` | Get general vehicle status | `range`, `charge` |
| `server v3 update all` | Force update of all metrics | |
| `charge` | Control charging | `start mode range`, `stop` |
| `climate` | Control climate system | `on temp 21`, `off` |
| `lock` | Lock/unlock vehicle | `on`, `off` |
| `location` | Get current location | |
| `valet` | Control valet mode | `on`, `off` |
| `config list` | List configuration parameters | `vehicle` |
| `metrics list` | List available metrics | `v.b.soc` |
| `feature` | Toggle features | `vehicle` |
| `notify raise` | Trigger notification | `alert.charge.stopped` |

Commands are rate limited to 5 per minute by default to prevent overwhelming the vehicle. The integration implements exponential backoff for reconnection attempts when connectivity is lost.

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

### Homelink Control

The integration provides a Homelink service that can trigger vehicle functions associated with Homelink buttons:

#### `ovms.homelink`
Activate a Homelink button on the OVMS module. 

```yaml
service: ovms.homelink
data:
  vehicle_id: your_vehicle_id
  button: 1  # Options: 1, 2, or 3
```

**Smart ForTwo-specific functionality:**
For Smart ForTwo vehicles, these buttons control climate functions:
- Button 1: 5 minute climate boost 
- Button 2: 10 minute climate boost
- Button 3: 15 minute climate boost or 12V battery charging

This feature requires a battery State of Charge (SoC) greater than 30%.

**Example Lovelace button configuration:**

```yaml
type: button
name: "5min Climate Boost"
icon: mdi:car-seat-heater
tap_action:
  action: call-service
  service: ovms.homelink
  service_data:
    vehicle_id: your_vehicle_id
    button: 1
```

## Communication Flow

The integration manages bidirectional communication between Home Assistant and your OVMS module:

### Data Flow: OVMS → Home Assistant
1. OVMS module publishes metrics to MQTT broker
2. Integration subscribes to all topics under the configured prefix
3. Messages are parsed to determine entity type and attributes
4. Entities are created or updated with the incoming data
5. Statistical processing is applied to relevant data (cell values, etc.)
6. Attributes are enriched with additional contextual information

![OVMS-Read-Flow](/assets/ovms-data-flow.svg)

### Command Flow: Home Assistant → OVMS
1. Service call is received with command parameters
2. Rate limiting is applied to prevent overwhelming the vehicle
3. Command is published to the appropriate MQTT topic
4. Integration subscribes to the corresponding response topic
5. Response is received and returned to the caller
6. Command state is updated based on the response

![OVMS-Write-Flow](/assets/ovms-command-flow.svg)

### Offline Detection and Recovery

The integration implements mechanisms for connection management:

- **Status Monitoring**: Vehicle online/offline status is tracked
- **Last Will and Testament**: MQTT "LWT" messages detect unexpected disconnections
- **Automatic Reconnection**: Reconnection with exponential backoff (increasing delays between attempts)
- **Connection Recovery**: When connection is restored, subscriptions are re-established
- **State Preservation**: Entity states are preserved during connection interruptions

## Location Tracking & GPS

The integration provides comprehensive location tracking:

### Combined Device Tracker

- Automatically creates a unified device tracker from separate latitude/longitude entities
- Maintains a single entity for location tracking that works with Home Assistant's map
- Updates latitude and longitude sensors when the tracker moves

### GPS Accuracy Estimation

- Calculates position accuracy based on GPS signal quality metrics
- Integrates HDOP (Horizontal Dilution of Precision) data when available
- Provides accuracy estimates in meters as an attribute
- Adjusts accuracy based on signal strength

*Example of the combined device tracker with accuracy information*

### State Preservation for Notification Topics in Home Assistant

Notification topics in Home Assistant are inherently transient, representing momentary events rather than persistent states. As a result, the associated sensors typically remain active for a limited period before transitioning to an `unavailable` status—this behavior is by design.

### Formal Solution for State Preservation

To maintain the state of notification topics and their corresponding sensors permanently, you can implement a template-based solution in Home Assistant. The following approach allows you to preserve the most recent state information:

```yaml
template:
  - sensor:
      - name: "Preserved Notification State"
        state: >
          {% if is_state('sensor.original_notification_topic', 'unavailable') %}
            {{ states('sensor.preserved_notification_state') }}
          {% else %}
            {{ states('sensor.original_notification_topic') }}
          {% endif %}
        availability: true
```

This template creates a persistent sensor that:
1. Retains the previous value when the original notification sensor becomes unavailable
2. Updates with new information when the original notification sensor is active
3. Remains continuously available regardless of the source sensor's status

### Implementation Considerations

When implementing this solution, you should:

- Replace `sensor.original_notification_topic` with the actual entity ID of your notification sensor
- Consider adding appropriate attributes to preserve additional contextual information
- Potentially include timestamp information to track when the last valid notification occurred

This approach provides a robust mechanism for maintaining notification states beyond their typical lifecycle, enabling more consistent automation and reporting capabilities.

## Technical Details

### Topic Structure

The integration supports these MQTT topic structures:

- Default: `ovms/username/vehicle_id/metric/...`
- Alternative: `ovms/client/vehicle_id/...`
- Simple: `ovms/vehicle_id/...`
- Custom: Define your own structure with placeholders

### Dynamic Topic Discovery

The integration implements sophisticated topic discovery:

- **Wildcard Subscription**: Uses MQTT wildcards to discover all relevant topics
- **Pattern Recognition**: Identifies topic structures even with different username patterns
- **Vehicle ID Extraction**: Automatically extracts vehicle IDs from discovered topics
- **Structure Detection**: Detects the actual topic structure being used by the OVMS module
- **Adaptive Subscription**: Subscribes to identified pattern for ongoing communication

This allows the integration to work even when the exact topic structure isn't known in advance.

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

### Entity Not Updating

1. Check if the OVMS module is still publishing data for that metric
2. Verify the topic hasn't changed
3. Try sending `server v3 update all` command to refresh all metrics
4. Check if there are any error messages in the logs

## FAQ

**Q: Can I use multiple vehicles with this integration?**  
A: Yes, you can set up multiple instances of the integration, one for each vehicle.

**Q: Does this work with all OVMS-supported vehicles?**  
A: Yes, the integration is vehicle-agnostic and works with any vehicle supported by OVMS. Vehicle-specific enhancements are provided for some models like VW e-UP!, Smart ForTwo, Nissan Leaf and MG ZS-EV.

**Q: Can I use this without internet access?**  
A: Yes, as long as your OVMS module, MQTT broker, and Home Assistant can communicate on the same network.

**Q: How frequent are the updates?**  
A: Updates happen in real-time as the OVMS module publishes new data, typically every few seconds while the vehicle is active.

**Q: How does the integration handle connectivity issues?**  
A: The integration includes automatic reconnection with exponential backoff, online/offline status tracking, and will resume normal operation when connection is restored.

**Q: Is my data secure?**  
A: Yes, the integration supports TLS/SSL encryption for MQTT connections and follows secure coding practices for handling sensitive data.

**Q: What happens if I lose connection to my vehicle?**  
A: The integration maintains the last known state of all entities and marks the vehicle as offline. When connection is restored, all entity states are updated with the latest data.

**Q: How can I see detailed information about cell voltages and temperatures?**  
A: This data is stored in entity attributes for the main battery sensors. Look at the attributes of your battery voltage and temperature entities to see detailed statistics.

**Q: Does the integration create separate sensors for each battery cell?**  
A: No, by default the integration calculates statistics (min, max, average, median) for cell data and stores these as attributes on a single sensor. This prevents cluttering your entities list with dozens of individual cell sensors.

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
