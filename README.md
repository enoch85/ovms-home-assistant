# OVMS MQTT Integration

This integration allows you to fetch all MQTT sensor values from the Open Vehicle Monitoring System (OVMS) into Home Assistant.
It's written by DeepSeek.

## Installation

1. Add this repository to HACS.
2. Install the integration.
3. Restart Home Assistant.

## First look:

![image](https://github.com/user-attachments/assets/8b8f44cd-356d-44ef-aad1-c3b60d3af8e6)

## Configuration

Add the following to your `configuration.yaml`:

```yaml
sensor:
  - platform: ovms_mqtt

