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

Version `0.1.0` is the first runtime scaffold. Appliance configuration and cycle
learning will be introduced incrementally while the private legacy implementation
is retained locally as migration reference.

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

Examples:

- `input_boolean.load_optimizer_1_learning_active`
- `input_text.load_optimizer_1_cycle_profile`
- `input_text.load_optimizer_1_learning_database`
- `input_number.load_optimizer_1_expected_runtime`
- `input_number.load_optimizer_1_expected_energy`

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
│   ├── migration.md
│   └── naming.md
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

Version `0.1.0` provides the installable App runtime, private persistence,
health monitoring, and a Home Assistant status sensor. Appliance instance
configuration, cycle learning, tariff analysis, and legacy migration are the
next development milestones.
