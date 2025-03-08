# OVMS Home Assistant Integration Overview

The info.md file provides a concise guide to the OVMS (Open Vehicle Monitoring System) integration for Home Assistant.

## Introduction

The OVMS integration connects your electric vehicle with Home Assistant via MQTT, automatically creating sensors for all vehicle metrics.

<details>
<summary>Read more about the integration purpose</summary>

The Open Vehicle Monitoring System (OVMS) is a hardware module that connects to electric vehicles to monitor and control various aspects of the vehicle. This integration serves as a bridge between that system and Home Assistant.

The integration works by:
- Connecting to the same MQTT broker that your OVMS module publishes data to
- Automatically discovering and creating Home Assistant entities for all the metrics your vehicle reports
- Providing services to send commands to your vehicle
- Maintaining real-time updates as new data is published

This allows you to incorporate your electric vehicle data into your smart home automation, dashboards, and monitoring systems. You can track battery levels, charging status, location, climate control settings, and more, depending on what your specific vehicle model supports through OVMS.
</details>

## Features

The integration offers automatic discovery, smart entity creation, real-time updates, command interface, and secure communication.

<details>
<summary>Read more about features</summary>

The integration provides several key features:

- **Automatic Discovery**: The integration detects all metrics published by your OVMS module to the MQTT broker. This means you don't need to manually configure each sensor - the integration will find and set up entities for all available data points automatically.

- **Smart Entity Creation**: Based on the type of data discovered, the integration creates appropriate Home Assistant entities. For example:
  - Battery percentages become battery sensors with proper device classes
  - Temperature readings become temperature sensors with appropriate units
  - Location data is represented as device trackers
  - Binary states (on/off, open/closed) become binary sensors

- **Real-time Updates**: The integration maintains a subscription to all relevant MQTT topics and updates Home Assistant entities immediately when new data is published. This ensures your dashboards and automations always have the latest information from your vehicle.

- **Command Interface**: Beyond just monitoring, the integration provides service calls that allow you to send commands to your vehicle. This enables features like:
  - Starting or stopping charging
  - Setting charging limits
  - Controlling the climate system
  - Sending any supported OVMS command

- **Secure Communication**: The integration supports TLS/SSL connections to your MQTT broker, ensuring that vehicle data and commands are transmitted securely.

These features make it possible to fully integrate your electric vehicle into your Home Assistant environment, both for monitoring and control purposes.
</details>

## Requirements

The integration requires Home Assistant (2023.10.0 or newer), MQTT integration, and an OVMS module publishing to the same broker.

<details>
<summary>Read more about requirements</summary>

To use this integration, you need:

- **Home Assistant** version 2023.10.0 or newer:
  The integration uses features and APIs that were introduced or stabilized in this version of Home Assistant. Earlier versions may not work correctly.

- **MQTT integration configured in Home Assistant**:
  Since this integration relies on MQTT for communication, you must have the MQTT integration set up and working in your Home Assistant instance. This includes:
  - A functioning MQTT broker (like Mosquitto, EMQX, or a cloud-based solution)
  - The Home Assistant MQTT integration properly configured to connect to this broker
  - Appropriate access permissions on the broker for both Home Assistant and OVMS

- **OVMS module publishing to the same MQTT broker**:
  Your Open Vehicle Monitoring System hardware module must be:
  - Running firmware that supports MQTT communication (3.3.001 or newer recommended)
  - Configured to publish data to the same MQTT broker that Home Assistant is connected to
  - If using authentication or access control on your broker, the OVMS module needs proper permissions to publish to its topics

The OVMS module itself needs to be properly installed and configured in your vehicle. The specifics of this installation depend on your vehicle make and model, and are outside the scope of the integration's documentation.
</details>

## Configuration

Configuration involves installing the integration, configuring the MQTT broker details, and entering the topic structure.

<details>
<summary>Read more about configuration steps</summary>

Setting up the OVMS integration involves several steps:

1. **Installing the Integration**:
   - Through HACS (Recommended):
     1. Add the repository to HACS: `https://github.com/enoch85/ovms-home-assistant`
     2. Install the integration through the HACS Integrations section
     3. Restart Home Assistant
   - Manually:
     1. Download the repository as a ZIP file
     2. Extract the `custom_components/ovms` folder to your Home Assistant's `custom_components` directory
     3. Restart Home Assistant

2. **MQTT Broker Configuration**:
   Before using the integration, your MQTT broker needs the correct permissions:
   - Subscribe permissions: `ovms/#` and `homeassistant/#`
   - Publish permissions: `ovms/+/+/client/rr/command/#` and `ovms/+/+/status`
   
   For brokers with restrictive ACLs (like Mosquitto or EMQX), ensure your MQTT user has these permissions.

3. **OVMS Module Configuration**:
   In your OVMS web UI:
   - Go to Config → Server V3 (MQTT)
   - Enter your broker details (address, port, credentials)
   - Set the topic prefix (default: `ovms`)
   - Enable Auto-Start

4. **Home Assistant Setup**:
   - Go to Settings → Devices & Services → Add Integration
   - Search for "OVMS" and select it
   - Enter your MQTT broker details
   - Configure the topic structure to match your OVMS settings
   - The integration will scan for available OVMS vehicles
   - Select your vehicle ID when prompted

After setup, the integration will automatically discover and create entities for all the metrics your OVMS module publishes. These will appear as sensors, binary sensors, or device trackers in Home Assistant, grouped under a device representing your vehicle.

For testing, you can enable debug logging by adding to your `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.ovms: debug
```
</details>

## Available Services

The integration provides services for sending commands, controlling climate and charging, and setting features.

<details>
<summary>Read more about services</summary>

The integration exposes several services that allow you to interact with your vehicle:

### `ovms.send_command`
This is the most versatile service, allowing you to send any command to the OVMS module.

```yaml
service: ovms.send_command
data:
  vehicle_id: your_vehicle_id
  command: stat
  parameters: range
  timeout: 10  # optional, seconds to wait for response
```

Example button configuration in Home Assistant:
```yaml
type: button
tap_action:
  action: perform-action
  perform_action: ovms.send_command
  data:
    vehicle_id: REG123
    command: server v3 update all
entity: input_button.ovms_update_all
name: "REG123: update all"
```

### `ovms.set_feature`
Set an OVMS configuration feature.

```yaml
service: ovms.set_feature
data:
  vehicle_id: your_vehicle_id
  feature: feature_name
  value: feature_value
```

### `ovms.control_climate`
Control the vehicle's climate system.

```yaml
service: ovms.control_climate
data:
  vehicle_id: your_vehicle_id
  temperature: 21.5
  hvac_mode: heat  # Options: heat, cool, auto, off
  duration: 30     # minutes
```

### `ovms.control_charging`
Control the vehicle's charging functions.

```yaml
service: ovms.control_charging
data:
  vehicle_id: your_vehicle_id
  action: start    # Options: start, stop, status
  mode: range      # Options: standard, storage, range, performance
  limit: 80        # percentage
```

These services enable automation of vehicle controls and integration with other Home Assistant systems. For example, you could create automations to:
- Start climate control when you leave work
- Stop charging when electricity prices are high
- Set different charging limits based on your calendar events
</details>

## Troubleshooting

The file includes instructions for enabling debug logging to troubleshoot integration issues.

<details>
<summary>Read more about troubleshooting</summary>

When encountering issues with the OVMS integration, debug logging can be extremely helpful in diagnosing problems. To enable debug logging, add the following to your `configuration.yaml` file:

```yaml
logger:
  default: info
  logs:
    custom_components.ovms: debug
```

After making this change, restart Home Assistant to apply it.

The debug logs will provide detailed information about:
- MQTT connection attempts
- Topic discovery processes
- Entity creation details
- Command sending and responses
- Message processing

This information can help identify issues related to:
- MQTT broker connection problems
- Permission issues (if your broker uses ACLs)
- Topic structure mismatches
- Command formatting errors
- Entity state update issues

**Important Note**: The debug output for this integration can be substantial, especially if you have many vehicle metrics or frequent updates. It's recommended to only enable debug logging temporarily while troubleshooting, as it may fill your logs quickly and potentially affect performance.

Other troubleshooting steps might include:
- Using external tools like MQTT Explorer to verify what your OVMS module is publishing
- Checking the Home Assistant MQTT integration logs for connection issues
- Verifying your OVMS module is correctly configured for MQTT publishing
- Ensuring the topic structure in the integration configuration matches what your OVMS module is using

If problems persist, collecting the debug logs along with your configuration details can be valuable when seeking support from the community or filing an issue on the GitHub repository.
</details>
