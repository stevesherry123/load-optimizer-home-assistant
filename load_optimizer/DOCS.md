# Load Optimizer

Load Optimizer is at an early public preview stage. This release establishes the
Home Assistant App runtime, persistent storage, health monitoring, and secure
communication with Home Assistant.

## Configuration

- **Log level** controls diagnostic detail.
- **Scan interval** controls how often the app refreshes its Home Assistant state.

## First start

Start the app and open its log. A successful start includes:

```text
Load Optimizer 0.1.0 started
```

Home Assistant will then expose `sensor.load_optimizer_status` with the state
`running`.

This preview does not yet monitor an appliance. Device instance configuration,
cycle learning, tariff analysis, and legacy migration will arrive in subsequent
versions.

## Data and authentication

The app stores its internal database in its private `/data` directory. Home
Assistant provides a temporary Supervisor credential automatically; no
long-lived access token is required.
