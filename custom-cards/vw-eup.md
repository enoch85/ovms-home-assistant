# VW e-UP

This is what I used myself (@enoch85). I'm sure it works for other cars as well, but thought I'd post it here for inspiration.

![image](https://github.com/user-attachments/assets/4aa80aa1-aad9-4f6b-a569-5d336b915324)

Replace `[car_name]` with your vehicle ID (e.g. `mycar123`).

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
          "--mdc-icon-size": 24px
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
              color: black
              "--mdc-icon-size": 16px
      - type: state-label
        entity: sensor.ovms_[car_name]_estimated_range
        suffix: " "
        style:
          top: 60%
          left: 60%
          font-size: 18px
          color: black
      - type: state-label
        entity: sensor.ovms_[car_name]_tire_emergency_values_vw_eup
        attribute: pressure_FR
        suffix: " kPa"
        style:
          top: 5%
          left: 20%
          font-weight: bold
          font-size: 16px
          color: black
      - type: state-label
        entity: sensor.ovms_[car_name]_tire_emergency_values_vw_eup
        attribute: pressure_RR
        suffix: " kPa"
        style:
          top: 5%
          left: 80%
          font-weight: bold
          font-size: 16px
          color: black
      - type: state-label
        entity: sensor.ovms_[car_name]_tire_emergency_values_vw_eup
        attribute: pressure_FL
        suffix: " kPa"
        style:
          top: 96%
          left: 20%
          font-weight: bold
          font-size: 16px
          color: black
      - type: state-label
        entity: sensor.ovms_[car_name]_tire_emergency_values_vw_eup
        attribute: pressure_RL
        suffix: " kPa"
        style:
          top: 97%
          left: 80%
          font-weight: bold
          font-size: 16px
          color: black
    image: /api/image/serve/[your_image_id]/512x512
    dark_mode_image: /api/image/serve/[your_dark_image_id]/512x512
  - type: entities
    title: OVMS Vehicle Status
    icon: mdi:car-electric
    entities:
      - entity: binary_sensor.ovms_[car_name]_status
        name: Status
        icon: mdi:information-outline
      - entity: binary_sensor.ovms_[car_name]_tire_alerts
        name: Tire status
        icon: mdi:tire
      - entity: binary_sensor.ovms_[car_name]_charging_status
        name: Charging Status
        icon: mdi:battery-charging
    state_color: true
  - type: grid
    columns: 3
    square: false
    cards:
      - type: gauge
        name: Battery Level
        entity: sensor.ovms_[car_name]_battery_level
        min: 0
        max: 100
        severity:
          green: 50
          yellow: 20
          red: 0
      - type: entity
        name: Ambient Temp
        entity: sensor.ovms_[car_name]_ambient_temperature
        icon: mdi:thermometer
      - type: entity
        name: Power
        entity: sensor.ovms_[car_name]_charge_power
        icon: mdi:flash
  - type: grid
    columns: 3
    square: false
    cards:
      - type: entity
        name: Odometer
        entity: sensor.ovms_[car_name]_odometer
        icon: mdi:counter
      - type: entity
        name: Speed
        entity: sensor.ovms_[car_name]_vehicle_speed
        icon: mdi:speedometer
      - type: entity
        name: Firmware
        entity: sensor.ovms_[car_name]_firmware_version
        icon: mdi:package-up
  - type: map
    title: Vehicle Location
    aspect_ratio: "16:9"
    default_zoom: 10
    entities:
      - entity: device_tracker.ovms_[car_name]_location
    theme_mode: auto
    hours_to_show: 24
```
