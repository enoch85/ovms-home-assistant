# VW e-UP 

This is what I used myself (@enoch85). I'm sure it works for other cars as well, but thought I'd post it here for inspiration.

![image](https://github.com/user-attachments/assets/4aa80aa1-aad9-4f6b-a569-5d336b915324)

```
type: vertical-stack
cards:
  - type: picture-elements
    elements:
      - type: state-label
        entity: sensor.ovms_[car_name]_metric_v_b_soc
        style:
          top: 45%
          left: 60%
          font-size: 36px
          font-weight: bold
          color: black
      - type: state-label
        entity: sensor.ovms_[car_name]_metric_v_b_range_est
        suffix: " "
        style:
          top: 60%
          left: 60%
          font-size: 18px
          color: black
      - type: conditional
        conditions:
          - entity: binary_sensor.ovms_[car_name]_metric_v_c_charging
            state: "on"
        elements:
          - type: icon
            icon: mdi:battery-charging
            style:
              top: 45%
              left: 47%
              color: green
              "--mdi-icon-size": 24px
      - type: state-label
        entity: sensor.ovms_[car_name]_metric_xvu_v_t_emgcy
        attribute: cell_1
        suffix: " kPa"
        style:
          top: 5%
          left: 20%
          font-weight: bold
          font-size: 16px
          color: black
      - type: state-label
        entity: sensor.ovms_[car_name]_metric_xvu_v_t_emgcy
        attribute: cell_3
        suffix: " kPa"
        style:
          top: 5%
          left: 80%
          font-weight: bold
          font-size: 16px
          color: black
      - type: state-label
        entity: sensor.ovms_[car_name]_metric_xvu_v_t_emgcy
        attribute: cell_2
        suffix: " kPa"
        style:
          top: 96%
          left: 20%
          font-weight: bold
          font-size: 16px
          color: black
      - type: state-label
        entity: sensor.ovms_[car_name]_metric_xvu_v_t_emgcy
        attribute: cell_4
        suffix: " kPa"
        style:
          top: 97%
          left: 80%
          font-weight: bold
          font-size: 16px
          color: black
    image: /api/image/serve/5a351bbcbcc82448b6cc121a7620c4bd/512x512
  - type: entities
    title: OVMS Vehicle Status
    icon: mdi:car-electric
    entities:
      - entity: binary_sensor.ovms_[car_name]_status
        name: Status
        icon: mdi:information-outline
      - entity: binary_sensor.ovms_[car_name]_metric_v_t_alert
        name: Tire status
        icon: mdi:tire
      - entity: binary_sensor.ovms_[car_name]_metric_v_c_charging
        name: Charging Status
        icon: mdi:battery-charging
    state_color: true
  - type: grid
    columns: 3
    square: false
    cards:
      - type: gauge
        name: Battery Level
        entity: sensor.ovms_[car_name]_metric_v_b_soc
        min: 0
        max: 100
        severity:
          green: 50
          yellow: 20
          red: 0
      - type: entity
        name: Ambient Temp
        entity: sensor.ovms_[car_name]_metric_v_e_temp
        icon: mdi:thermometer
      - type: entity
        name: Power
        entity: sensor.ovms_[car_name]_metric_v_c_power
        icon: mdi:flash
  - type: grid
    columns: 3
    square: false
    cards:
      - type: entity
        name: Odometer
        entity: sensor.ovms_[car_name]_metric_v_p_odometer
        icon: mdi:counter
      - type: entity
        name: Speed
        entity: sensor.ovms_[car_name]_metric_v_p_speed
        icon: mdi:speedometer
      - type: entity
        name: Firmware
        entity: sensor.ovms_[car_name]_metric_m_version
        icon: mdi:package-up
  - type: map
    title: Vehicle Location
    aspect_ratio: "16:9"
    default_zoom: 10
    entities:
      - entity: device_tracker.ovms_[car_name]_location
    hours_to_show: 24
```
