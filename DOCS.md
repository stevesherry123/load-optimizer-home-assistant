# Load Optimizer

Load Optimizer monitors a configurable appliance through Home Assistant, detects
its power cycles, and retains completed-cycle statistics in private app storage.

## Configuration

- **Log level** controls diagnostic detail.
- **Scan interval** controls how often the app refreshes its Home Assistant state.
- **Instance 1 name** is the friendly appliance name, such as `Dishwasher 1`.
- **Power sensor** is required for cycle detection.
- **Energy, program, and state sensors** are optional but improve cycle records.
- **Active power threshold** is the wattage above which a cycle is considered active.
- **Finish delay** is the number of consecutive scans below that threshold before a cycle ends.

## First start

Start the app and open its log. A successful start includes:

```text
Load Optimizer 0.5.0 started
```

Home Assistant exposes `sensor.load_optimizer_status` and a set of
`sensor.load_optimizer_1_*` entities. Until a power sensor is configured,
`sensor.load_optimizer_1_status` reports `configuration_required`.

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
published through `sensor.load_optimizer_1_program_policies`.

### Example configuration

The following example configures one appliance and classifies its `PreRinse`
program as an alternative that will not be selected automatically:

```yaml
log_level: info
scan_interval: 60
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
```

Replace the four `sensor.your_appliance_*` values with entities from the local
Home Assistant installation. Do not publish private device-specific entity IDs
when sharing configuration publicly.

The two recommendation flags default to `false` when omitted. Setting a
classification alone never grants permission for the scheduler to use a program.

## Data and authentication

The app stores its internal database in its private `/data` directory. Home
Assistant provides a temporary Supervisor credential automatically; no
long-lived access token is required.
