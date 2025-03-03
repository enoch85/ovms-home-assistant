# OVMS MQTT Integration

This integration allows you to fetch all MQTT sensor values from the Open Vehicle Monitoring System (OVMS) into Home Assistant.
It's written by DeepSeek.

## WIP

The current implementation doesn't work. If you want to test it you need to manually move [this folder](https://github.com/enoch85/ovms-mqtt-integration/tree/main/custom_components/ovms_mqtt) to your Home Assistant and activate the integration.

In it's current state, it installs fine, and produces no errors, but [no enteties are produced](https://github.com/enoch85/ovms-mqtt-integration/issues/12).

## Installation

1. Add this repository to HACS.
2. Install the integration.
3. Restart Home Assistant.

## First look:

![image](https://github.com/user-attachments/assets/e369aa7b-fce1-440e-ac7f-b93ae69cf726)

## Configuration

Add the following to your `configuration.yaml`:

```yaml
sensor:
  - platform: ovms_mqtt

