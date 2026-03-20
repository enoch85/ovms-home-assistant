# Renault Twizy

This is a sample dashboard card for the Renault Twizy. You can customize it to your needs.

![image](https://github.com/user-attachments/assets/placeholder-for-image.png)

Replace `[car_name]` with your vehicle ID as configured in OVMS (e.g. `mycar123`), and place a Renault Twizy image at `/local/images/renault_twizy.png` in your Home Assistant configuration.

```yaml
type: vertical-stack
cards:
  - type: picture-elements
    elements:
      - type: state-label
        entity: sensor.ovms_[car_name]_battery_level
        style:
          top: 45%
          left: 60%
          font-size: 36px
          font-weight: bold
          color: black
      - type: state-icon
        entity: sensor.ovms_[car_name]_battery_level
        style:
          top: 45%
          left: 47%
          "--mdi-icon-size": 24px
      - type: conditional
        conditions:
          - entity: binary_sensor.ovms_[car_name]_charging_status
            state: "on"
        elements:
          - type: icon
            icon: mdi:flash
            style:
              top: 45%
              left: 47%
              color: green
              "--mdi-icon-size": 24px
      - type: state-label
        entity: sensor.ovms_[car_name]_estimated_range
        suffix: " "
        style:
          top: 60%
          left: 60%
          font-size: 18px
          color: black
      - type: state-label
        entity: sensor.ovms_[car_name]_available_energy_renault_twizy
        prefix: "Available: "
        suffix: " kWh"
        style:
          top: 70%
          left: 60%
          font-size: 14px
          color: black
      - type: state-label
        entity: sensor.ovms_[car_name]_total_energy_renault_twizy
        prefix: "Total: "
        suffix: " kWh"
        style:
          top: 75%
          left: 60%
          font-size: 14px
          color: black
    image: /local/images/renault_twizy.png
    aspect_ratio: 16:9
  - type: glance
    entities:
      - entity: sensor.ovms_[car_name]_odometer
        name: Odometer
      - entity: sensor.ovms_[car_name]_estimated_range
        name: Range
      - entity: sensor.ovms_[car_name]_battery_consumption
        name: Consumption
  - type: entities
    entities:
      - entity: sensor.ovms_[car_name]_battery_level
        name: State of Charge
      - entity: sensor.ovms_[car_name]_battery_current
        name: Battery Current
      - entity: sensor.ovms_[car_name]_battery_voltage
        name: Battery Voltage
      - entity: sensor.ovms_[car_name]_battery_temperature
        name: Battery Temperature
      - entity: sensor.ovms_[car_name]_battery_power
        name: Battery Power
    title: Battery
  - type: entities
    entities:
      - entity: sensor.ovms_[car_name]_actual_torque_renault_twizy
        name: Actual Torque
      - entity: sensor.ovms_[car_name]_inverter_power_renault_twizy
        name: Inverter Power
      - entity: sensor.ovms_[car_name]_inverter_temperature
        name: Inverter Temperature
    title: Motor
```
