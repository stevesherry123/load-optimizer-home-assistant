# EV Charging Skeleton

This is the first-pass EV charging load type for the Load Optimizer HACS
integration. It adds recommendations without committing to charger control.

## Observed Volvo Entities

From the pasted Home Assistant state list, the useful starting entities are:

- `sensor.volvo_xc60_battery`: current battery percentage, seen as `1.0`.
- `sensor.volvo_xc60_battery_capacity`: usable battery capacity, seen as
  `18.819` kWh.
- `sensor.volvo_xc60_target_battery_charge_level`: target percentage, seen as
  `100`.
- `sensor.volvo_xc60_charging_connection_status`: plug status, seen as
  `disconnected`.
- `sensor.volvo_xc60_estimated_charging_time`: car-provided estimate, seen as
  `0.0`.
- `sensor.volvo_xc60_estimated_charging_finish_time`: car-provided finish time.
- `switch.volvo_charger`: possible charger switch, but currently `unavailable`
  in the pasted state.

The current skeleton only plans. It does not turn `switch.volvo_charger` on or
off.

## v1.0 Integration Shape

The HACS integration is configured through Home Assistant's UI rather than the
legacy add-on `instances_yaml` option. A Volvo-oriented setup maps roughly to:

- name: `Volvo XC60`
- load type: `ev_charging`
- battery entity: `sensor.volvo_xc60_battery`
- battery capacity entity: `sensor.volvo_xc60_battery_capacity`
- target percentage entity:
  `sensor.volvo_xc60_target_battery_charge_level`
- connection status entity:
  `sensor.volvo_xc60_charging_connection_status`
- charge power: household charger rating in kW
- charger efficiency: default `0.9`
- slot length: default `30`
- ready by: optional local `HH:MM`

Open questions:

- Is `sensor.volvo_xc60_battery` a percentage for this car, or a normalized
  fraction where `1.0` means 100%?
- What is the real charge power at home when the charger is available?
- Should Load Optimizer target the Volvo target entity, always 100%, or a
  user-configured target?
- Should negative prices allow charging beyond the target if the vehicle permits
  it, or should the target remain a hard cap?
- Should a later optional Home Assistant automation package control the charger,
  or should examples remain enough?

## Planning Module

The integration planner lives at
`custom_components/load_optimizer/optimizer/ev_charging.py`.

- `plan_ev_charge(...)` accepts normalized tariff periods and chooses the
  cheapest required charging slots.

The planner uses the existing tariff period shape:

```python
{"start": datetime, "end": datetime, "price_p_per_kwh": 12.34}
```

It returns:

- readiness status and reason
- estimated kWh needed
- wall energy after charger efficiency
- selected charging slots
- estimated total cost in pence
- estimated profit in pence when the selected plan is net negative
- whether the current time is inside a selected slot

## Published Entities

The v1.0 integration publishes advisory entities such as:

- `sensor.<name>_status`
- `sensor.<name>_estimated_cost`
- `sensor.<name>_estimated_profit`
- `sensor.<name>_needed_battery_energy`
- `sensor.<name>_wall_energy`
- `sensor.<name>_next_slot_start`
- `binary_sensor.<name>_charge_now`
- `binary_sensor.<name>_ready_to_charge`

Automation should remain a separate opt-in Home Assistant package, matching the
current architecture principle that Load Optimizer recommends and household
automation decides whether to execute.
