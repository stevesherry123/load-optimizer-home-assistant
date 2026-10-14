# Advisory EV Planning

Add a separate entry and choose `ev_charging`. This calculates charging slots;
it does **not** operate a charger, car or plug. Any separate charger automation
needs its own safety checks and explicit opt-in.

## Setup Fields

| Field | Example / meaning |
| --- | --- |
| Tariff entity | One entity with usable future rates. EV setup currently has no additional-entities list. A current-price-only sensor is insufficient. |
| Tariff price unit | `gbp_per_kwh` for Octopus `value_inc_vat` values such as `0.25`; `p_per_kwh` for values such as `25`. |
| Tariff timezone | `Europe/London` for UK tariff days and the ready-by deadline. |
| Battery percentage entity | Numeric `sensor`, for example 40, not `0.4`, range or remaining kWh. |
| Battery capacity entity | Numeric `sensor` with usable capacity in kWh, for example 60. Select an entity, not the number itself. |
| Target percentage entity | Optional numeric sensor. If absent or nonnumeric, the fallback target is used. |
| Connection status entity | Optional text `sensor`: `connected` / `disconnected`. Unknown/unavailable data blocks planning; an omitted input is assumed available for advisory planning. |
| Charge power | Expected wall charging power in **kW**, for example `7.2`, not 7200 W. |
| Fallback target percentage | For example `80`. Use your manufacturer's appropriate target. |
| Charger efficiency | A fraction: `0.9` means 90%, not the number 90. |
| Slot length | Minutes, normally `30` for half-hourly tariffs. |
| Ready by | Optional next local `HH:MM`, for example `07:00`, not an ISO date. Leave blank for the available horizon. |
| Ofgem region / payment method | A comparison benchmark, not a change to charging prices or the live tariff's region. |

Edit inputs later through the EV Configure cog. This preserves entry and entity
identities; do not delete and recreate the entry just to edit.

## When The Vehicle Has No Capacity Sensor

A template sensor can expose known usable capacity. Merge into the existing
`template:` configuration, avoiding duplicate top-level keys, and replace **60**
with the correct usable capacity for your vehicle:

```yaml
template:
  - sensor:
      - name: EV usable battery capacity
        unique_id: ev_usable_battery_capacity
        unit_of_measurement: kWh
        device_class: energy
        state: "60"
```

Check the resulting entity ID and value before selecting it. Use HA's configuration
check and template-entity reload or appropriate restart after adding configuration.
A fixed value is an assumption, not a measurement of degradation or charging speed.

## When Connection Is A Binary Sensor

The picker currently accepts only a text `sensor`. Do not relabel raw `on`/`off`:
they are not a supported disconnected-state convention. Adapt to explicit text,
preserving missing-data behaviour:

```yaml
template:
  - sensor:
      - name: EV charging connection
        unique_id: ev_charging_connection
        state: >-
          {% if is_state('binary_sensor.ev_plugged_in', 'on') %}
            connected
          {% elif is_state('binary_sensor.ev_plugged_in', 'off') %}
            disconnected
          {% else %}
            unavailable
          {% endif %}
```

Replace the binary entity ID, merge any existing `template:` section and verify
connected, disconnected and unavailable cases before selecting the new sensor.
This advisory signal is not a charger electrical-safety interlock.

## Check The Plan

With sufficient usable rates, the EV device shows Status `ready`, needed battery
energy, wall energy, estimated cost and next-slot start. For a 60 kWh battery at
40% with an 80% target and 0.9 efficiency, it needs 24 kWh into the battery and
about 26.67 kWh from the wall. Whole-slot rounding can select slightly more.

`ready_to_charge` means a complete plan exists. `charge_now` is true only during a
selected slot of a ready plan; future slots are not a command to charge now.
An already met target produces no slots and both signals are off. Charging taper,
actual efficiency and vehicle limits can change real outcomes.

For `not_ready`, inspect the Status `reason` attribute and follow
[troubleshooting](troubleshooting.md#ev-planning). This guide installs no
charger-switch automation.
