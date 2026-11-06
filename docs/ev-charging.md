# Advisory EV Planning

Add a separate entry and choose `ev_charging`. This calculates charging slots;
it remains advisory by default. The unreleased development build also provides
[optional switch control](ev-control.md), requiring configured feedback and a
separate Automatic Charging opt-in.

The [control guide](ev-control.md) describes activation, confirmation and recovery.
No control is enabled by saving the EV form.

## Charging Modes (Unreleased Development Build)

- **Required charging:** use the cheapest available slots, including paid
  electricity, to aim for the target by Ready by. If available charging cannot
  reach it, recommend the useful charging that is possible and show the expected
  remaining shortfall. No selected interval extends beyond the deadline.
- **Opportunistic charging:** use only prices at or below the configured ceiling.
  The default ceiling is **0 p/kWh**, allowing free and negative prices. The target
  remains an upper limit, with no promise that the available cheap slots reach it.

Existing entries without a mode setting retain **required** mode. Edit the mode
through the existing EV Configure form; entries, devices and entity IDs are
retained. Saving leaves Automatic Charging off; optional control requires its separate switch. The new modes and partial-plan
behaviour are development work, not a published or installed update.

## Setup Fields

The [generic EV form example](examples/ev-planning.yaml) and separate
[optional switch fields](examples/ev-switch-control.yaml) are exercised by the
isolated Home Assistant acceptance checks. Replace their entity IDs and numeric
assumptions; they are form values, not a configuration.yaml integration block.

| Field | Example / meaning |
| --- | --- |
| Tariff entity | One entity with usable future rates. Use Additional future-rate entities to combine separate published forecasts in the development build. A current-price-only sensor is insufficient. |
| Tariff price unit | `gbp_per_kwh` for Octopus `value_inc_vat` values such as `0.25`; `p_per_kwh` for values such as `25`. |
| Tariff timezone | `Europe/London` for UK tariff days and the ready-by deadline. |
| Battery percentage entity | Numeric `sensor`, for example 40, not `0.4`, range or remaining kWh. |
| Battery capacity entity | Numeric `sensor` with usable capacity in kWh, for example 60. Select an entity, not the number itself. |
| Target percentage entity | Optional numeric sensor. If absent or nonnumeric, the fallback target is used. |
| Connection status entity | Optional text sensor or, in the development build, a binary sensor. Recognised available states are `connected`, `charging`, `plugged_in` and `on`. Disconnected, unknown, unavailable or unrecognised states block planning. An omitted reference is assumed available for advisory planning; a configured reference that disappears blocks planning. |
| Additional future-rate entities (unreleased) | Optional list, for example the Octopus next-day rates event alongside the current-day event as primary. Empty or unavailable sources are disclosed; only published intervals are used. |
| Optional charger power switch (unreleased) | Power switch controlled only after explicit Automatic Charging activation. |
| Optional charger measured power (unreleased) | Sensor in W or kW, required with charger controls. |
| Optional car charging status (unreleased) | Slower corroborating feedback; does not replace a power meter or cable-connection sensor. |
| Command confirmation timeout (unreleased) | 30–600 seconds, default 180. |
| Charging mode (unreleased) | `required` or `opportunistic`; existing entries default to required. |
| Opportunistic price ceiling (unreleased) | Pence per kWh, independent of the tariff source's input unit. Inclusive: a ceiling of 0 allows exactly zero and negative prices. Required mode ignores this ceiling. |
| Charge power | Expected wall charging power in **kW**, for example `7.2`, not 7200 W. |
| Fallback target percentage | For example `80`. Use your manufacturer's appropriate target. |
| Charger efficiency | A fraction: `0.9` means 90%, not the number 90. |
| Slot length | Minutes, normally `30` for half-hourly tariffs. |
| Ready by | Optional next local `HH:MM`, for example `07:00`, not an ISO date. Leave blank to plan within the available rates, bounded to seven days. Set a deadline when completion time matters. |
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

The development build accepts a connected binary sensor directly: `on` means
connected, while `off` and unavailable states block planning. The following
text adapter remains useful for older releases or custom source mappings,
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
about 26.67 kWh from the wall. The development build shortens the final interval
to the remaining energy estimate instead of planning a whole extra slot. It also
uses the remaining minutes of an active tariff interval after a refresh between
half-hour boundaries. Unpriced gaps are never filled with assumed free energy.

In the development build:

| Result | Meaning |
| --- | --- |
| Required `ready` | The selected plan is expected to reach the target. |
| Required `partial` | Useful charging is selected, but a shortfall remains. |
| Opportunistic `ready` | Eligible cheap charging is selected; the target may remain out of reach. |
| Opportunistic `waiting` | No available slots meet the ceiling. This is not a source failure. |
| `not_ready` | Inputs are unavailable/invalid, or no usable charging opportunity exists. |

**Changed signal semantics:** `ready_to_charge` now means a usable advisory plan
exists, including required partial plans. It no longer proves the complete target
is reachable. Use `target_reachable` separately for that assessment. `charge_now`
is true during a selected interval even when the target has a shortfall. These
signals describe the latest scan; they are not charger commands or precision
start/stop timers. Optional native control supplies its own interval timers and
revalidation; avoid running conflicting external charger automations. Review external automations that relied on the old complete-plan
meaning before adopting this development build.

The plan exposes `planned_wall_energy_kwh`, `planned_battery_kwh`,
`projected_battery_percent`, `shortfall_battery_kwh`, `target_reachable`, the chosen
mode and a readable summary. An already met target selects no slots and turns
both charging signals off. Charging taper, actual efficiency, SOC reporting delays
and vehicle limits can change the real outcome.

The cost estimate covers electricity and charging losses. The legacy
`estimated_profit_pence` value is retained as an electricity-credit estimate;
`estimated_electricity_credit_pence` names that meaning explicitly. Neither
includes vehicle wear or other operating costs, so it is not a whole-vehicle
profit calculation.

For Ready by times in a repeated clock-change hour, use the next remaining
occurrence. A time skipped by the spring clock change moves forward by that
change. Invalid clock settings or timezones block planning rather than silently
removing the deadline.

## Optional Plan Card

Add a manual Markdown card using [the EV plan card example](examples/ev-plan-card.yaml).
Replace its single `sensor.your_ev_status` reference with the **Status** entity
from your EV device. It shows the mode, projected charge, shortfall, electricity
cost and selected intervals in Home Assistant's local time. It contains no control
actions. The card requires the matching development integration for the new fields.

For `not_ready`, inspect the Status `reason` attribute and follow
[troubleshooting](troubleshooting.md#ev-planning). This guide installs no
charger-switch automation.
