# OVMS Home Assistant

The Open Vehicle Monitoring System (OVMS) integration for Home Assistant. Connect your electric vehicle with Home Assistant via MQTT, automatically creating sensors for all vehicle metrics.

## Features

- **Automatic Discovery**: Detects all metrics published by your OVMS module
- **Smart Entity Creation**: Creates appropriate sensors based on data type
- **Real-time Updates**: Entities update as new data is published
- **Command Interface**: Send commands to your vehicle through services
- **Secure Communication**: Supports TLS/SSL connections

## Requirements

- Home Assistant (2023.10.0 or newer)
- MQTT integration configured in Home Assistant
- OVMS module publishing to the same MQTT broker

## Configuration

1. Configure your OVMS module to publish to your MQTT broker
2. Install this integration through HACS
3. Add the integration in Home Assistant
4. Enter your MQTT broker details and topic structure
5. Your vehicle's metrics will appear as entities

## Available Services

- `ovms.send_command`: Send any command to your vehicle
- `ovms.control_climate`: Control the vehicle's climate system
- `ovms.control_charging`: Control charging functions
- `ovms.set_feature`: Configure OVMS parameters

## Troubleshooting

Enable debug logging by adding to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.ovms: debug
```

Check the logs for detailed information about discovered topics and entities.
