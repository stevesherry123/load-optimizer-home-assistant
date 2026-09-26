# Load Optimizer


Load Optimizer is a Home Assistant integration for scheduling flexible
electrical loads around dynamic tariffs, deadlines, and negative-price windows.

It is designed to be device-agnostic. Dishwashers, washing machines, EVs, home
batteries, immersion heaters, and future load types should be handled as
adapters on top of one shared optimisation core.

## v1.0 Integration Preview

The integration line moves Load Optimizer from the original Home Assistant
add-on to a HACS custom integration.

The integration supports two setup paths:

- **Learned appliance migration**: runs the existing add-on engine inside the
  integration and publishes the same `sensor.load_optimizer_*` entities.
- **EV charging**: reads an existing battery percentage entity, battery capacity
  entity, target percentage, charger power, and future tariff entity, then
  publishes the cheapest charging windows required to reach the target.

The integration is advisory in v1.0. It publishes sensors and binary sensors
for automations, but it does not directly switch a charger on or off.

### HACS Installation

Until this repository is included as a default HACS repository, add it as a
custom repository:

```text
https://github.com/stevesherry123/load-optimizer-home-assistant
```

Choose category **Integration**, install **Load Optimizer**, restart Home
Assistant, then add **Load Optimizer** from Settings > Devices & services.

For public/stable installs, use tagged releases. The HACS metadata hides the
default branch so ordinary users are not nudged toward development builds.

### Add-on Migration

To migrate the existing add-on, create a Load Optimizer integration entry with
load type `learned_appliance`, paste your existing add-on `instances_yaml` and
tariff settings, then import the old `/data/load_optimizer.json` database with
the `load_optimizer.import_legacy_state` service.

See `docs/migration-addon-to-integration.md`.

### EV Entities

For a Volvo-style setup, the config flow can use entities such as:

- `sensor.volvo_xc60_battery`
- `sensor.volvo_xc60_battery_capacity`
- `sensor.volvo_xc60_target_battery_charge_level`
- `sensor.volvo_xc60_charging_connection_status`

The tariff entity can be any Home Assistant entity exposing future rates in one
of the formats already supported by the original Load Optimizer tariff parser,
including `ai_feed`, `rates`, `prices`, `forecast`, or `all_rates`.

## Legacy Add-on

The existing Home Assistant add-on remains in this repository during the
migration. It continues to contain the learned appliance-cycle engine,
dishwasher automation examples, dashboards, and historical documentation.

Add-on installation still uses the Home Assistant add-on store URL:

```text
https://github.com/stevesherry123/load-optimizer-home-assistant
```

The add-on path is retained for existing users while the integration grows to
cover the same learned appliance functionality.

## Goals

- Schedule flexible electrical loads from normalized tariff data.
- Keep supplier integrations optional and provider-neutral.
- Publish advisory entities that Home Assistant automations can safely consume.
- Retain the learned appliance-cycle engine during the integration migration.
- Add EV charging as the first v1.0 integration load type.

## Design Principles

- Use a shared core for tariff parsing and optimisation.
- Treat each load as a configured Home Assistant integration entry.
- Keep device-specific logic in adapters only.
- Keep physical control opt-in and household-owned.

## Naming Convention

The legacy add-on uses the instance-based namespace:

- `load_optimizer_1_*` for the first appliance instance
- `load_optimizer_2_*` for the second appliance instance
- future adapters can map their own device-specific sensors into the same shared model

For each configured add-on instance, the add-on publishes examples such as:

- `sensor.load_optimizer_N_status`
- `sensor.load_optimizer_N_power`
- `sensor.load_optimizer_N_energy`
- `sensor.load_optimizer_N_cycle_state`
- `sensor.load_optimizer_N_last_runtime`
- `sensor.load_optimizer_N_last_energy`
- `sensor.load_optimizer_N_last_profile`
- `sensor.load_optimizer_N_learned_programs`
- `sensor.load_optimizer_N_program_model`
- `sensor.load_optimizer_N_program_policies`
- `sensor.load_optimizer_N_cost_status`
- `sensor.load_optimizer_N_cheapest_start`
- `sensor.load_optimizer_N_cheapest_cost`
- `sensor.load_optimizer_N_recommended_program`

The v1.0 integration creates entities under the normal Home Assistant integration
device model, such as:

- `sensor.<name>_status`
- `sensor.<name>_estimated_cost`
- `sensor.<name>_estimated_profit`
- `sensor.<name>_needed_battery_energy`
- `sensor.<name>_wall_energy`
- `sensor.<name>_next_slot_start`
- `binary_sensor.<name>_charge_now`
- `binary_sensor.<name>_ready_to_charge`

## Current Scope

The integration v1.0 scope is:

- HACS-compatible custom integration structure.
- UI configuration flow.
- EV charging slot planning from existing Home Assistant entities.
- Tariff parsing inherited from the original add-on core.
- Cost and profit estimates for selected charging windows.
- Binary advisory state for "charge now".

The learned-appliance compatibility runtime is now the preferred path for
migrating existing add-on installations. Keep the add-on stopped once the
integration is publishing the expected entities.

## Roadmap

Planned work and backlog ideas are tracked in `docs/roadmap.md`.

## Repository Layout

```text
.
├── README.md
├── repository.yaml
├── hacs.json
├── custom_components/
│   └── load_optimizer/
├── load_optimizer/
│   ├── app/
│   ├── config.yaml
│   ├── Dockerfile
│   ├── DOCS.md
│   └── run.sh
├── homeassistant/
│   ├── dashboards/
│   └── packages/
├── docs/
│   ├── architecture.md
│   ├── naming.md
│   └── roadmap.md
└── tests/
```

## Public-State Model

The shared state model should focus on:

- active cycle status
- current program or mode
- cycle start timestamp
- start energy reading
- live profile samples
- peak power
- last completed cycle data
- learned aggregate database
- human-readable summary

## Project Status

The project is entering the v1.0 integration migration. The HACS integration is
the public direction for new development; the Home Assistant add-on remains in
place for existing learned-appliance functionality.

Optional Home Assistant packages and dashboard snippets are stored in
`homeassistant/`.
