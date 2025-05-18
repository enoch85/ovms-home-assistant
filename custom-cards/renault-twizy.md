# Renault Twizy

This is a sample dashboard card for the Renault Twizy. You can customize it to your needs.

![image](https://github.com/user-attachments/assets/placeholder-for-image.png)

```yaml
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
        entity: sensor.ovms_[car_name]_metric_xrt_b_energy_avail
        prefix: "Available: "
        suffix: " kWh"
        style:
          top: 70%
          left: 60%
          font-size: 14px
          color: black
      - type: state-label
        entity: sensor.ovms_[car_name]_metric_xrt_b_energy_full
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
      - entity: sensor.ovms_[car_name]_metric_v_p_odometer
        name: Odometer
      - entity: sensor.ovms_[car_name]_metric_v_b_range_est
        name: Range
      - entity: sensor.ovms_[car_name]_metric_v_b_consumption
        name: Consumption
  - type: entities
    entities:
      - entity: sensor.ovms_[car_name]_metric_v_b_soc
        name: State of Charge
      - entity: sensor.ovms_[car_name]_metric_v_b_current
        name: Battery Current
      - entity: sensor.ovms_[car_name]_metric_v_b_voltage
        name: Battery Voltage
      - entity: sensor.ovms_[car_name]_metric_v_b_temp
        name: Battery Temperature
      - entity: sensor.ovms_[car_name]_metric_v_b_power
        name: Battery Power
    title: Battery
  - type: entities
    entities:
      - entity: sensor.ovms_[car_name]_metric_xrt_i_trq_act
        name: Actual Torque
      - entity: sensor.ovms_[car_name]_metric_xrt_i_pwr_act
        name: Inverter Power
      - entity: sensor.ovms_[car_name]_metric_v_i_temp
        name: Inverter Temperature
    title: Motor
```

Replace `[car_name]` with your vehicle ID as configured in OVMS, and place a Renault Twizy image at `/local/images/renault_twizy.png` in your Home Assistant configuration.
