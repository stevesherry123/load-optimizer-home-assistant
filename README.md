# Load Optimizer

Load Optimizer is a Home Assistant automation project for learning appliance cycle profiles, estimating running cost from energy tariffs, and recommending the best time and mode to run a load.

It is designed to be device-agnostic from the start. Dishwasher, washing machine, and future EV or other load types should be handled as instance adapters on top of one shared core.

## Home Assistant App Installation

This project is moving to a self-contained Home Assistant App. Add this repository
to the Home Assistant Apps store:

```text
https://github.com/stevesherry123/load-optimizer-home-assistant
```

Install **Load Optimizer**, start it, and confirm that
`sensor.load_optimizer_status` reports `running`.

Version `0.7.0` supports multiple configured appliance instances. Configure
`instance_ids` on the App's **Configuration** tab, for example `1` for just the
dishwasher or `1,2` for dishwasher plus washing machine, then restart the App.
Each instance publishes its own `sensor.load_optimizer_N_*` monitoring and cost
entities.

## Goals

- Learn cycle power profiles over time.
- Estimate runtime, energy use, and cost from learned data.
- Recommend economical start times.
- Recommend the best program or cycle when the appliance offers a choice.
- Keep entity names consistent, public, and migration-friendly.

## Design Principles

- Use a shared core for cycle tracking and optimisation.
- Treat each appliance as an instance, using `1` for the first one.
- Keep device-specific logic in adapters only.
- Migrate existing helper state forward where possible.
- Retire legacy entities after the new structure is stable.

## Naming Convention

Use the instance-based namespace everywhere:

- `load_optimizer_1_*` for the first appliance instance
- `load_optimizer_2_*` for the second appliance instance
- future adapters can map their own device-specific sensors into the same shared model

For each configured instance, the App publishes examples such as:

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

## Current Scope

The first public implementation should support:

- cycle start detection
- live sampling
- cycle completion
- learned summaries
- dashboard status cards
- cost estimation
- migration from legacy dishwasher and washing machine helpers

## Roadmap Highlights

Upcoming design work is focused on richer scheduling and recommendation logic:

- per-instance earliest start and latest finish constraints
- profile-weighted cost estimation across tariff windows
- active recommended-window state for dashboards and automations
- manual recalculation after tariff, policy, or configuration changes
- inferred cycle classification for appliances that only expose power usage

See `docs/architecture.md` for the fuller roadmap and design notes.

## Repository Layout

```text
.
├── README.md
├── repository.yaml
├── load_optimizer/
│   ├── app/
│   ├── config.yaml
│   ├── Dockerfile
│   ├── DOCS.md
│   └── run.sh
├── docs/
│   ├── architecture.md
│   ├── deployment.md
│   ├── home_assistant_config.md
│   ├── migration.md
│   ├── naming.md
│   └── validation.md
└── homeassistant/
    ├── adapters/
    ├── dashboards/
    ├── helpers/
    ├── legacy/
    ├── migrations/
    ├── packages/
    ├── pyscript/
    └── templates/
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

The installable App scaffold is now the future-facing runtime. The existing
`homeassistant/` files remain temporarily as migration reference and will be
retired after their behavior and data have moved into the App.

For rollout, use:

- `docs/deployment.md`
- `docs/validation.md`
