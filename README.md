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

Version `0.3.0` adds the first configurable appliance instance and automatically
publishes its `sensor.load_optimizer_1_*` monitoring entities. Configure the
source entities on the App's **Configuration** tab, then restart the App.

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

The App now publishes examples such as:

- `sensor.load_optimizer_1_status`
- `sensor.load_optimizer_1_power`
- `sensor.load_optimizer_1_energy`
- `sensor.load_optimizer_1_cycle_state`
- `sensor.load_optimizer_1_last_runtime`
- `sensor.load_optimizer_1_last_energy`
- `sensor.load_optimizer_1_last_profile`

## Current Scope

The first public implementation should support:

- cycle start detection
- live sampling
- cycle completion
- learned summaries
- dashboard status cards
- cost estimation
- migration from legacy dishwasher and washing machine helpers

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
