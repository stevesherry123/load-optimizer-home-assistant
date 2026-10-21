# Advisory EV Planning

Released EV planning remains advisory. The isolated, unreleased
[`feature/ev-charger-control` prototype](ev-control-development.md) adds opt-in
switch control and metered delivery checks; real-EV physical acceptance remains
open. An approved owner-only installation uses a separate simulated-battery,
small-load test entry. Its extra fields are not available in existing releases.
That branch also includes a read-only review dashboard and a
[hardware-free step-through preview](ev-control-development.md#read-only-dashboard-and-offline-review)
with fictional negative prices; the offline preview cannot change Home Assistant.

## Guided Setup On The Development Branch

The unreleased EV branch now offers a guided path for new entries and under
**Configure > Guided EV setup and plan review** for existing EV entries:

1. Select tariff, battery percentage, capacity, target and connection sources.
2. Set charging power, efficiency, ready-by time, session allowances and optional
   charger feedback/control entities. Leave the switch empty for advisory only.
3. Review current input checks and proposed cheapest charging slots. Refresh the
   preview or return to either earlier screen before saving.
4. Optionally select an existing storage-mode dashboard, such as Load Optimizer,
   to append a read-only charging view. Existing views and cards are preserved.

No settings are committed before the final save, and the review never commands
a switch or contacts a cloud API. Saving rechecks current readings. Missing,
stale or incorrectly unit-labelled inputs require correction or an explicit
**Save with warnings for advisory use** acknowledgement. That acknowledgement
does not bypass the running controller's safety checks or turn it on.
Saving an existing controlled entry reloads it and stops any owned session;
charger activation is a separate, explicit action after reviewing the saved plan.

The appended view uses built-in Markdown cards only; it does not require
ApexCharts or replace the existing price graph. It includes battery/plan data,
selected slots, delivery feedback and input freshness. An existing view at the
entry's generated path is never overwritten, including any user edits. Changing
the destination or clearing the setting does not delete previously added views.
YAML-mode and automatically generated overview dashboards are not written to.
Inspect the review sensor's `dashboard_status` if the optional append fails;
the integration continues to work without a dashboard view.

The advanced single-form editor remains available. Neither this wizard nor its
synthetic tests constitute real-EV physical acceptance. Installation and a
supervised Volvo trial remain separate deployment steps.

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
