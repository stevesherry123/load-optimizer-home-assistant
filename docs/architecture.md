# Architecture

## Overview

Load Optimizer is split into three layers:

1. Core learning and optimisation logic
2. Device adapters
3. Home Assistant entity and dashboard surfaces

The core must not depend on Bosch, Home Connect, washing machine-specific logic, or any other single appliance.

## Core Responsibilities

- Detect when a cycle starts.
- Sample power during the cycle.
- Detect when a cycle ends.
- Build and maintain learned summaries.
- Estimate cost for a future run.
- Select an economical start window.

## Device Adapter Responsibilities

Each adapter should:

- read device-specific sensors
- normalize program names
- decide when a cycle is active
- map live state into the shared model
- expose only the minimum device-specific concepts needed by the core

## Home Assistant Responsibilities

Home Assistant should be used for:

- source power, energy, program, and state sensors
- tariff entities from any compatible supplier integration or custom source
- published `sensor.load_optimizer_*` entities from the App
- dashboards, notifications, and automations built on top of those sensors

## Canonical Entities

The first appliance instance should use the `load_optimizer_1_*` namespace.

Published App sensors include:

- `sensor.load_optimizer_1_status`
- `sensor.load_optimizer_1_power`
- `sensor.load_optimizer_1_energy`
- `sensor.load_optimizer_1_program`
- `sensor.load_optimizer_1_cycle_state`
- `sensor.load_optimizer_1_sample_count`
- `sensor.load_optimizer_1_peak_power`
- `sensor.load_optimizer_1_last_program`
- `sensor.load_optimizer_1_last_runtime`
- `sensor.load_optimizer_1_last_energy`
- `sensor.load_optimizer_1_last_finish`
- `sensor.load_optimizer_1_last_profile`
- `sensor.load_optimizer_1_total_runs`
- `sensor.load_optimizer_1_learned_programs`
- `sensor.load_optimizer_1_program_model`
- `sensor.load_optimizer_1_program_policies`
- `sensor.load_optimizer_1_cost_status`
- `sensor.load_optimizer_1_cheapest_start`
- `sensor.load_optimizer_1_cheapest_cost`
- `sensor.load_optimizer_1_cost_if_started_now`
- `sensor.load_optimizer_1_potential_saving`
- `sensor.load_optimizer_1_cost_confidence`
- `sensor.load_optimizer_1_recommended_program`

## Data Flow

1. Adapter reads live device sensors.
2. Core decides whether the instance is idle, active, or finishing.
3. Core stores sampled power into the current profile.
4. Core writes end-of-cycle summary data.
5. Core updates the learned database.
6. App sensors expose learned values, cost estimates, and recommendations.

## Persistence Strategy

The supported runtime stores internal data in the App's private `/data`
directory and publishes Home Assistant sensors for visibility.

That gives:

- a clean public installation path
- app-owned persistence that does not require user-managed helpers
- transparent read-only state for dashboards and automations

## Energy Measurement

Status: Active design principle

Completed-cycle energy should be calculated from captured power samples wherever
possible. Integrating the power profile avoids common problems with daily energy
counters, including:

- multiple cycles on the same day
- cycles that span midnight
- source sensors that reset, round, or lag unexpectedly

Energy sensors can still be exposed and retained as diagnostic metadata, but the
learned model should prefer profile-integrated energy so the same approach works
across dishwashers, washing machines, EVs, and other future load types.

## Scheduling Model

Status: Active design principle

Scheduling should be split into two separate concepts:

- **Constraints** define which candidate starts are allowed.
- **Strategies** decide which allowed candidate is preferred.

This distinction keeps the app device-agnostic and avoids mixing user intent
with safety rules.

Examples of constraints:

- earliest allowed start
- latest allowed finish
- must finish before a deadline
- avoid a calendar window
- only start during an overnight or daytime window
- only allow selected programs

Examples of strategies:

- `cheapest_earliest_finish`: choose the cheapest acceptable slot, but prefer the
  earliest finish among near-equivalent candidates
- `cheapest_latest_finish`: choose the cheapest acceptable slot, but prefer the
  latest finish among near-equivalent candidates
- `cheapest_absolute`: choose the mathematically cheapest candidate even if it
  delays the run for a very small saving

A deadline is therefore not the same as a strategy. A deadline narrows the valid
window; a strategy ranks the remaining valid options. For a dishwasher before
travel, the likely model is a deadline constraint plus `cheapest_earliest_finish`. For a
future EV or battery use case, the likely model is a departure deadline plus
`cheapest_latest_finish`.

The current App runtime exposes advisory scheduling entities only. It should not
start appliances until constraints, confidence thresholds, and user permissions
have been proven through read-only operation.

## Calendar And Deadline Context

Status: Recommended full-automation direction

Calendar integration is not required for core learning, cost estimation, or
basic cheapest-start recommendations. It is recommended for the full scheduling
experience because real households have deadlines and availability windows that
cannot be inferred from tariff data alone.

Calendar or helper-driven deadlines should allow the app to answer questions
such as:

- must the cycle finish before travel?
- is there a household deadline tomorrow morning?
- should an appliance avoid running while the user is away?
- is a cheap slot still useful if it finishes after the user needs the appliance?

TripIt is a recommended travel-calendar source because it can automatically
convert flights, rail, hotels, and itinerary emails into calendar events exposed
to Home Assistant. Other Home Assistant calendar entities should also be
supported where they provide reliable upcoming events.

The preferred implementation path is:

1. Add Home Assistant helper-based deadline inputs as the stable app contract.
2. Let user automations, including TripIt automations, populate those helpers.
3. Later add direct calendar polling as a convenience layer.

This keeps the app useful for people who do not use TripIt while still providing
a clear recommended setup for travel-aware scheduling.

## Roadmap Boundaries

Planned work, backlog items, and future feature ideas live in
`docs/roadmap.md`. This keeps the architecture document focused on the current
shape and design principles of the system.

## Retired Local Infrastructure

The earlier local appliance packages, templates, helper definitions, dashboards,
and Pyscript files are no longer part of the repository. Future contributions
should target the supported App runtime and avoid reintroducing app-managed
`dishwasher_*` or `washing_machine_*` helper namespaces.
