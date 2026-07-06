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
Load Optimizer 0.2.0 started
```

Home Assistant exposes `sensor.load_optimizer_status` and a set of
`sensor.load_optimizer_1_*` entities. Until a power sensor is configured,
`sensor.load_optimizer_1_status` reports `configuration_required`.

## Data and authentication

The app stores its internal database in its private `/data` directory. Home
Assistant provides a temporary Supervisor credential automatically; no
long-lived access token is required.
