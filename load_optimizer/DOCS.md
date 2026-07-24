# Load Optimizer

Load Optimizer monitors a configurable appliance through Home Assistant, detects
its power cycles, and retains completed-cycle statistics in private app storage.

## Configuration

- **Log level** controls diagnostic detail.
- **Scan interval** controls how often the app refreshes its Home Assistant state.
- **Scalable appliance instances** is the YAML or JSON text field used to define
  appliances. Add one list item per appliance and give each item a stable
  numeric `id`.
- **Reset instance IDs** is normally blank. Set it to a comma-separated list
  such as `2` to clear selected learned instance data on the next app start.
  The request is one-shot while the same value remains configured, and
  `sensor.load_optimizer_status` reports whether it is pending, consumed, or
  invalid.
- **Instance N name** is the friendly appliance name, such as `Dishwasher 1` or
  `Washing Machine 1`.
- **Power sensor** is required for cycle detection.
- **Energy, program, and state sensors** are optional but improve cycle records.
- **Active power threshold** is the wattage above which a cycle is considered active.
- **Finish delay** is the number of consecutive scans below that threshold before a cycle ends.

## First start

Start the app and open its log. A successful start includes:

```text
Load Optimizer 0.8.30 started
```

Home Assistant exposes `sensor.load_optimizer_status` and a set of
`sensor.load_optimizer_N_*` entities for each configured instance. Until a power
sensor is configured, that instance's status reports `configuration_required`.

After a completed cycle, `sensor.load_optimizer_1_last_profile` exposes the
timestamped power samples in its `samples` attribute. Each compact sample is
`[offset_seconds, power_w]`, allowing dashboards and future tariff calculations
to align the profile without depending on a particular appliance or integration.
Completed-cycle energy is calculated from these power samples where possible,
which avoids daily energy counter reset issues when a cycle spans midnight or
when multiple cycles run on the same day.

## Program learning

Completed cycles are grouped by their normalized program name. The app maintains
expected runtime, energy, peak power, variation, confidence, and a representative
20-point power profile without retaining an ever-growing list of raw cycles.

- `sensor.load_optimizer_1_learned_programs` summarizes every learned program.
- `sensor.load_optimizer_1_program_model` exposes the latest program model.
- Confidence grows over the first five consistent runs and falls when observed
  runtime or energy varies significantly.

## Program policies

Program policies are configured separately from learned measurements. Each
policy can classify a program as `preferred`, `alternative`, `maintenance`,
`opportunistic`, `disabled`, or `unclassified`, and can control normal and
negative-price eligibility, preference rank, cooldown, run limits, and estimated
non-energy operating costs.

Newly learned programs default to `unclassified` and are not eligible for a
recommendation until the user makes an explicit choice. Resolved policy is
published through `sensor.load_optimizer_N_program_policies`.

The app also publishes `sensor.load_optimizer_N_program_catalogue`, which merges
learned programs and explicitly configured policies. This makes planned cycles
visible before they have any learned runs. For example, a configured
`MachineCare` policy appears with `runs: 0` and
`status: configured_unlearned` until the appliance has completed that cycle.

Newly observed learned programs with no explicit policy are also exposed through
`sensor.load_optimizer_N_discovered_programs`. These entries are safe by
default: they are not eligible for normal or negative-price recommendations
until the user adds a policy.

### Example configuration

Use the `instances_yaml` text field for every appliance. Home Assistant's add-on
options UI does not provide reliable unlimited dynamic rows, so the app treats
this field as the source of truth for instance configuration.

The following example configures a dishwasher as instance `1`, a washing
machine as instance `2`, and leaves room to add future appliances without new
app fields:

```yaml
log_level: info
scan_interval: 60
reset_instance_ids: ""
publish_diagnostics: false
publish_profile_data: true
publish_cost_forecast: true
instances_yaml: |
  - id: "1"
    name: Dishwasher 1
    power_sensor: sensor.your_appliance_power
    energy_sensor: sensor.your_appliance_energy
    program_sensor: sensor.your_appliance_active_program
    state_sensor: sensor.your_appliance_operation_state
    active_power_threshold: 10
    finish_delay: 5
    program_policies:
      - program: PreRinse
        classification: alternative
        enabled: true
        preference_rank: 50
        allow_normal_recommendation: false
        allow_negative_price_run: false
        minimum_days_between_runs: 0
        minimum_hours_between_runs: 0
        maximum_runs_per_window: 0
        negative_price_priority: 50
        fixed_cost_pence: 0
        water_litres: 0
        water_cost_pence_per_litre: 0
        wear_cost_pence: 0

  - id: "2"
    name: Washing Machine 1
    power_sensor: sensor.your_washing_machine_power
    energy_sensor: sensor.your_washing_machine_energy
    program_sensor: ""
    state_sensor: ""
    active_power_threshold: 5
    finish_delay: 2
    program_policies: []
```

Replace the four `sensor.your_appliance_*` values with entities from the local
Home Assistant installation. Do not publish private device-specific entity IDs
when sharing configuration publicly.

The two recommendation flags default to `false` when omitted. Setting a
classification alone never grants permission for the scheduler to use a program.

`minimum_hours_between_runs` is the preferred cooldown field. Older
`minimum_days_between_runs` values are still accepted and are converted to hours
when the hours field is omitted. During scheduling, candidates that would start
before the program's latest learned finish plus this cooldown are rejected. This
lets the optimiser fall through to the next eligible program instead of
repeating the same cycle while still building confidence in alternatives.
Cooldown decisions are exposed in `program_diagnostics` with
`reason: cooldown_active` and `cooldown_until` where applicable.

`maximum_runs_per_window: 0` means unlimited for future negative-price planning.
`negative_price_priority` ranks explicitly allowed negative-price programs
before energy intensity is used as a tie-breaker.

Operating-cost fields let the recommendation show a more realistic cycle cost
than electricity alone:

- `fixed_cost_pence`: fixed per-run consumables, such as a dishwasher tablet.
- `water_litres`: estimated water consumed by this program.
- `water_cost_pence_per_litre`: household water and wastewater cost.
- `wear_cost_pence`: optional depreciation or wear-and-tear allowance.

The app calculates `non_energy_cost_pence` from those fields and adds it to the
tariff-based electricity estimate. Older configurations using
`estimated_overhead_cost_pence` still work; it is treated as
`fixed_cost_pence`.

Negative-price opportunity detection still uses the energy-cost component so
that genuinely negative electricity windows are not hidden by tablet, water, or
wear estimates. Published recommendation attributes expose both
`energy_cost_pence` and `non_energy_cost_pence`, with `cost_pence` representing
the combined total.

Only `program` and `classification` are required. All other policy fields are
optional and use the conservative defaults published in the
`optional_field_defaults` attribute of
`sensor.load_optimizer_N_program_policies`.

## Operational Safeguards

If the app starts while an instance already has an active cycle capture, Home
Assistant receives a persistent notification. This can happen during manual
restarts, host restarts, or public auto-updates. The app marks that active
capture as interrupted. When it later finishes, the cycle is published as a
discarded cycle and is not loaded into the learned programme model.

The app also publishes `sensor.load_optimizer_restart_safety`. It reports
`blocked` while any appliance cycle capture is active, and `safe` when no
capture is in progress. Use this on dashboards before applying add-on updates,
or in automations that announce when it is unsafe to restart Home Assistant or
the add-on.

The main status entity also exposes `active_capture_instances` so dashboards and
debugging views can show whether any appliance was mid-cycle at the last update.
It also exposes `restart_blocked` for simple dashboard conditions.

Discarded interrupted cycles are visible through
`sensor.load_optimizer_N_last_discarded_cycle`, including the programme, finish
time, runtime, energy, sample count, and exclusion reason.

The app also applies learning quality gates before accepting a completed cycle.
By default, a cycle is excluded if it is shorter than 5 minutes, has fewer than
3 samples, or uses less than 0.001 kWh. These conservative defaults prevent
brief threshold blips, partial captures, and restart artefacts from poisoning the
learned program model. If a recent-cycle model already contains a suspicious
entry, the app removes that entry during startup, reduces the affected run
counts, and clears any representative profile that may have absorbed the bad
shape data. Future valid cycles rebuild the profile.

Advanced users can override these thresholds per appliance in `instances_yaml`:

```yaml
learning_min_runtime_minutes: 5
learning_min_samples: 3
learning_min_energy_kwh: 0.001
```

To clear contaminated learning data for a single instance, set
`reset_instance_ids` and restart the app:

```yaml
reset_instance_ids: "2"
```

The same reset request is processed only once while it remains configured, so an
accidentally lingering value will not repeatedly wipe new data on every restart.
`sensor.load_optimizer_status` exposes reset feedback attributes including
`reset_status`, `reset_requested_instance_ids`, `reset_processed_instance_ids`,
`reset_pending_instance_ids`, `reset_invalid_tokens`, and `reset_message`.

After confirming the instance has reset, you may still set it back to:

```yaml
reset_instance_ids: ""
```

Clearing the field also re-arms it, allowing the same instance to be reset again
later if needed.

## Cost estimation

Cost estimation is optional and read-only. Set **Tariff entities** to one or
more comma-separated Home Assistant entities containing future electricity
prices. The older **Tariff entity** field remains supported for a single source.

Each tariff source can contain either:

- an `ai_feed` attribute such as `06/07 00:00=18.41p;`, or
- a structured `rates`, `prices`, `forecast`, or `all_rates` list containing
  start, end, and price values.

Load Optimizer does not depend on Octopus Intelligence or any particular energy
supplier. OIE's forecast entity is one compatible source, while other integrations
can provide structured rates. Leave both tariff fields blank to disable costing.

Treat tariff and environmental data as provider inputs. The app should stay a
generic load optimiser: Octopus, BottlecapDave's Octopus Energy integration,
manual tariff helpers, solar forecasts, battery sensors, and future non-UK
tariff providers are all optional sources of context rather than core
requirements.

For BottlecapDave's Octopus Energy integration, prefer the upstream rate event
entities directly, for example:

```yaml
tariff_entities: "event.octopus_energy_electricity_xxx_current_day_rates,event.octopus_energy_electricity_xxx_next_day_rates"
tariff_price_unit: gbp_per_kwh
```

Any Home Assistant entity that exposes one of the supported rate formats can be
used. Avoid publishing private entity IDs in shared examples.

Use **Tariff price unit** to declare whether structured values are pence or pounds
per kWh. The `ai_feed` format includes its `p` unit and is always interpreted as
pence per kWh. The app normalizes timestamps to UTC, scales each representative
profile to its learned measured energy, and rejects estimates when rates do not
cover the complete cycle.

The first release searches configurable start intervals over the next 24 hours
and publishes recommendations only; it never starts an appliance.

- `sensor.load_optimizer_N_cost_status`
- `sensor.load_optimizer_N_cost_if_started_now`
- `sensor.load_optimizer_N_now_recommendation`
- `sensor.load_optimizer_N_soon_recommendation`
- `sensor.load_optimizer_N_overnight_recommendation`
- `sensor.load_optimizer_N_negative_price_recommendation`
- `sensor.load_optimizer_N_cheapest_start`
- `sensor.load_optimizer_N_cheapest_cost`
- `sensor.load_optimizer_N_overnight_cost`
- `sensor.load_optimizer_N_daytime_cost`
- `sensor.load_optimizer_N_potential_saving`
- `sensor.load_optimizer_N_overnight_saving`
- `sensor.load_optimizer_N_daytime_saving`
- `sensor.load_optimizer_N_cost_confidence`
- `sensor.load_optimizer_N_recommended_program`
- `sensor.load_optimizer_N_cost_forecast`

The overnight and daytime comparison entities show the best eligible option in
each start window, independent of which option is selected as the current
recommendation. This makes dashboards clearer: users can compare overnight
cost, daytime cost, cost if started now, and the saving for each option.

The recommendation entities are intended for simple front ends such as Alexa,
dashboard buttons, mobile notifications, or physical switches. The state is the
recommended program when ready, while attributes include `start`, `finish`,
`cost_pence`, `saving_vs_now_pence`, `confidence`, `ready_to_start`, and
`reason`. A voice workflow can therefore offer "start now or schedule overnight"
without duplicating tariff or policy logic outside the app.

The cost forecast entity publishes chart-ready forecast data in its `forecast`
attribute. Each row contains the learned program, candidate start and finish,
estimated cost, learned energy, confidence, and whether the start is overnight or
daytime. By default the forecast covers the next 12 hours:

```yaml
cost_forecast_hours: 12
cost_forecast_interval: 30
publish_diagnostics: false
publish_profile_data: true
publish_cost_forecast: true
```

`cost_forecast_interval` controls chart granularity only. The optimiser can keep
using a smaller `cost_candidate_interval` for precise recommendations while the
forecast chart shows cleaner half-hourly points.

### Storage-conscious publishing

Load Optimizer keeps learned data in its private app storage, then publishes a
dashboard-friendly subset to Home Assistant entities. To reduce database growth
on smaller Raspberry Pi installations, repeated unchanged entity states are not
republished, and large diagnostic attributes are disabled by default.

- `publish_diagnostics: false` omits verbose tariff, forecast, breakdown, and
  program diagnostics from routine entity attributes.
- `publish_profile_data: true` keeps the compact chart payload available for
  profile dashboards. Set it to `false` if disk space is more important than
  profile charts.
- `publish_cost_forecast: true` keeps the forecast chart payload available. Set
  it to `false` if cost forecast charts are not used.

For very tight SD-card installations, Home Assistant Recorder exclusions can
also be used. This is optional, but useful if dashboards do not need historical
copies of the larger derived attributes:

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.load_optimizer_*_last_profile
      - sensor.load_optimizer_*_profile_data
      - sensor.load_optimizer_*_cost_forecast
      - sensor.load_optimizer_*_program_model
      - sensor.load_optimizer_*_learned_programs
      - sensor.load_optimizer_*_program_policies
      - sensor.load_optimizer_*_program_catalogue
      - sensor.load_optimizer_*_discovered_programs
```

The scheduling layer is advisory-only. It republishes the current recommendation
as explicit start guidance and a safe automation signal, but it does not call any
service or start an appliance.

- `sensor.load_optimizer_N_schedule_status`
- `sensor.load_optimizer_N_recommended_start`
- `sensor.load_optimizer_N_recommended_finish`
- `sensor.load_optimizer_N_estimated_scheduled_cost`
- `sensor.load_optimizer_N_good_to_start`

`good_to_start` turns `on` only when the recommended start is within the
configured tolerance window. The `automation_ready` attribute is stricter: it
also requires the recommendation confidence to meet the configured threshold.
Defaults are conservative: confidence at least `20` and start within `5`
minutes. Advanced users can override these per appliance in `instances_yaml`:

```yaml
schedule_confidence_threshold: 20
schedule_start_tolerance_minutes: 5
```

Future scheduling work will separate constraints from strategy. Constraints
define what is allowed, such as a latest finish deadline. Strategy decides which
allowed slot to prefer, such as `cheapest_earliest_finish` for dishwashers or
`cheapest_latest_finish` for EV-style loads.

Future provider-aware scheduling may also compare the cheapest candidate with a
greener candidate. For example, an Octopus user may expose a greener-nights
calendar, while another household may expose a local carbon-intensity sensor or
solar/battery forecast. The intended model is to publish both the financial
best option and the greener option, including the extra cost of choosing the
greener run. This should remain optional and supplier-agnostic.

To enable green-window comparison, set **Green window entity** to a Home
Assistant calendar or entity that exposes preferred greener windows. The app
does not require Octopus, but BottlecapDave's Octopus Energy greener-nights
calendar is a suitable source when available:

```yaml
green_window_entity: calendar.octopus_energy_xxx_greener_nights
```

The app will continue to publish the cheapest recommendation, then additionally
publish the best candidate that overlaps a green window:

- `sensor.load_optimizer_N_greenest_recommendation`
- `sensor.load_optimizer_N_greenest_cost`
- `sensor.load_optimizer_N_greenest_extra_cost`

`greenest_extra_cost` is the extra cost of choosing the greener candidate rather
than the cheapest candidate. If no green-window entity is configured, or no
candidate overlaps a green window, these entities remain `unknown` or
`not_ready`.

To prevent discretionary loads during provider events, set **Blocked window
entity** to a Home Assistant calendar or entity that exposes no-run windows.
This is intended for events such as Octoplus Saving Sessions, where the best
financial outcome comes from reducing consumption compared with the household's
normal usage during the event:

```yaml
blocked_window_entity: calendar.octopus_energy_xxx_octoplus_saving_sessions
```

Blocked windows are stricter than green windows. Any candidate that overlaps a
blocked window is removed from normal recommendations and cost forecasts. Cost
entities publish the configured blocked-window source, the number of windows
found, and the number of rejected candidate starts so dashboards can explain
why some normally good slots were skipped.

Supported strategy values are:

- `cheapest_absolute`: choose the mathematically cheapest candidate.
- `cheapest_earliest_finish`: among candidates within the configured cost
  tolerance of the cheapest option, choose the one that finishes earliest.
- `cheapest_latest_finish`: among candidates within the configured cost
  tolerance of the cheapest option, choose the one that finishes latest.

```yaml
schedule_strategy: cheapest_earliest_finish
schedule_equivalent_cost_tolerance_pence: 1.0
```

Schedule windows can be used to restrict or prefer daytime and overnight starts.
By default, overnight is 20:00-08:00 in the configured tariff timezone.

Supported values:

- `any`: no window preference
- `overnight_only`: only recommend starts in the overnight window
- `daytime_only`: only recommend starts outside the overnight window
- `prefer_overnight`: prefer overnight starts when cost is near-equivalent
- `prefer_daytime`: prefer daytime starts when cost is near-equivalent

```yaml
schedule_window_preference: prefer_overnight
schedule_overnight_start: "20:00"
schedule_overnight_end: "08:00"
```

Calendar integration is recommended for the full automation experience because
it lets the scheduler understand travel, household deadlines, and avoid windows.
TripIt is a good travel-calendar source because it can automatically populate a
Home Assistant calendar from itinerary emails, but basic learning and cost
recommendations do not require TripIt or any calendar.

For travel-aware scheduling, point an appliance at editable Home Assistant
datetime helpers. The app treats future helper values as constraints and ignores
empty, unavailable, or past values:

```yaml
schedule_latest_finish_entity: input_datetime.load_optimizer_1_must_finish_by
```

The optional example package
`homeassistant/packages/load_optimizer_travel_deadline_example.yaml` creates that
helper and shows a TripIt-style calendar automation. The example seeds the
must-finish-by helper to 90 minutes before the travel event, while leaving the
helper editable so the household can adjust the deadline before the optimiser
acts on it.

Ready cost entities include a `cost_breakdown` attribute where applicable. Each
entry shows the tariff period start/end, the price in pence per kWh, the learned
cycle energy allocated to that period, and the resulting cost. This is important
for long-running appliances: a cycle can continue into an expensive period while
most of its high-power work happened earlier during a cheap, free, or negative
price window.

Expected non-ready states include `tariff_not_configured`, `tariff_unavailable`,
`tariff_invalid`, `no_eligible_programs`, and `insufficient_profile`.

## Data and authentication

The app stores its internal database in its private `/data` directory. Home
Assistant provides a temporary Supervisor credential automatically; no
long-lived access token is required.
