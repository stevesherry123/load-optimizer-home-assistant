# Load Optimizer

Load Optimizer monitors a configurable appliance through Home Assistant, detects
its power cycles, and retains completed-cycle statistics in private app storage.

## Configuration

- **Log level** controls diagnostic detail.
- **Scan interval** controls how often the app refreshes its Home Assistant state.
- **Instance IDs** is a comma-separated list of appliance instances to monitor,
  such as `1` or `1,2`.
- **Instance N name** is the friendly appliance name, such as `Dishwasher 1` or
  `Washing Machine 1`.
- **Power sensor** is required for cycle detection.
- **Energy, program, and state sensors** are optional but improve cycle records.
- **Active power threshold** is the wattage above which a cycle is considered active.
- **Finish delay** is the number of consecutive scans below that threshold before a cycle ends.

## First start

Start the app and open its log. A successful start includes:

```text
Load Optimizer 0.7.0 started
```

Home Assistant exposes `sensor.load_optimizer_status` and a set of
`sensor.load_optimizer_N_*` entities for each configured instance. Until a power
sensor is configured, that instance's status reports `configuration_required`.

After a completed cycle, `sensor.load_optimizer_1_last_profile` exposes the
timestamped power samples in its `samples` attribute. Each compact sample is
`[offset_seconds, power_w]`, allowing dashboards and future tariff calculations
to align the profile without depending on a particular appliance or integration.

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
non-energy overhead.

Newly learned programs default to `unclassified` and are not eligible for a
recommendation until the user makes an explicit choice. Resolved policy is
published through `sensor.load_optimizer_N_program_policies`.

### Example configuration

The following example configures a dishwasher as instance `1` and a washing
machine as instance `2`. The dishwasher `PreRinse` program is classified as an
alternative that will not be selected automatically:

```yaml
log_level: info
scan_interval: 60
instance_ids: "1,2"
instance_1_name: Dishwasher 1
instance_1_power_sensor: sensor.your_appliance_power
instance_1_energy_sensor: sensor.your_appliance_energy
instance_1_program_sensor: sensor.your_appliance_active_program
instance_1_state_sensor: sensor.your_appliance_operation_state
instance_1_active_power_threshold: 10
instance_1_finish_delay: 5
instance_1_program_policies:
  - program: PreRinse
    classification: alternative
    enabled: true
    preference_rank: 50
    allow_normal_recommendation: false
    allow_negative_price_run: false
    minimum_days_between_runs: 0
    maximum_runs_per_window: 1
    estimated_overhead_cost_pence: 0

instance_2_name: Washing Machine 1
instance_2_power_sensor: sensor.your_washing_machine_power
instance_2_energy_sensor: sensor.your_washing_machine_energy
instance_2_program_sensor: sensor.your_washing_machine_active_program
instance_2_state_sensor: sensor.your_washing_machine_operation_state
instance_2_active_power_threshold: 10
instance_2_finish_delay: 5
instance_2_program_policies: []
```

Replace the four `sensor.your_appliance_*` values with entities from the local
Home Assistant installation. Do not publish private device-specific entity IDs
when sharing configuration publicly.

The two recommendation flags default to `false` when omitted. Setting a
classification alone never grants permission for the scheduler to use a program.

Only `program` and `classification` are required. All other policy fields are
optional and use the conservative defaults published in the
`optional_field_defaults` attribute of
`sensor.load_optimizer_N_program_policies`.

## Cost estimation

Cost estimation is optional and read-only. Set **Tariff entity** to a Home
Assistant entity containing either:

- an `ai_feed` attribute such as `06/07 00:00=18.41p;`, or
- a structured `rates`, `prices`, `forecast`, or `all_rates` list containing
  start, end, and price values.

Load Optimizer does not depend on Octopus Intelligence or any particular energy
supplier. OIE's forecast entity is one compatible source, while other integrations
can provide structured rates. Leave the tariff entity blank to disable costing.

Use **Tariff price unit** to declare whether structured values are pence or pounds
per kWh. The `ai_feed` format includes its `p` unit and is always interpreted as
pence per kWh. The app normalizes timestamps to UTC, scales each representative
profile to its learned measured energy, and rejects estimates when rates do not
cover the complete cycle.

The first release searches configurable start intervals over the next 24 hours
and publishes recommendations only; it never starts an appliance.

- `sensor.load_optimizer_N_cost_status`
- `sensor.load_optimizer_N_cost_if_started_now`
- `sensor.load_optimizer_N_cheapest_start`
- `sensor.load_optimizer_N_cheapest_cost`
- `sensor.load_optimizer_N_potential_saving`
- `sensor.load_optimizer_N_cost_confidence`
- `sensor.load_optimizer_N_recommended_program`

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
