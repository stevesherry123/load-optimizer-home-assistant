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

- helper entities for persistence
- template sensors
- scripts and automations
- dashboards

## Canonical Entities

The first appliance instance should use the `load_optimizer_1_*` namespace.

Suggested core helpers:

- `input_boolean.load_optimizer_1_learning_active`
- `input_text.load_optimizer_1_cycle_program`
- `input_text.load_optimizer_1_cycle_profile`
- `input_number.load_optimizer_1_cycle_sample_count`
- `input_datetime.load_optimizer_1_cycle_start`
- `input_number.load_optimizer_1_cycle_start_energy`
- `input_number.load_optimizer_1_peak_power`
- `input_text.load_optimizer_1_last_program`
- `input_number.load_optimizer_1_last_runtime_minutes`
- `input_number.load_optimizer_1_last_energy_kwh`
- `input_datetime.load_optimizer_1_last_finish`
- `input_text.load_optimizer_1_learning_database`
- `input_text.load_optimizer_1_learning_summary`

Suggested prediction helpers:

- `input_number.load_optimizer_1_expected_runtime`
- `input_number.load_optimizer_1_expected_energy`

Suggested display sensors:

- `sensor.load_optimizer_1_selected_program`
- `sensor.load_optimizer_1_cycle_state`
- `sensor.load_optimizer_1_recommendation`
- `sensor.load_optimizer_1_scheduled_start`

## Data Flow

1. Adapter reads live device sensors.
2. Core decides whether the instance is idle, active, or finishing.
3. Core stores sampled power into the current profile.
4. Core writes end-of-cycle summary data.
5. Core updates the learned database.
6. Prediction helpers expose learned values to the dashboard and scheduler.

## Persistence Strategy

The first version will remain Home Assistant-native and helper-based.

That gives:

- easy migration from the existing setup
- transparent state for dashboards
- a community-friendly installation path

## True Operating Cost

Status: Backlog / deferred

Initial optimisation will use electricity cost only.

Future versions may calculate a broader operating cost incorporating:

- water consumption
- detergent and other consumables
- appliance wear
- battery degradation for applicable devices
- other configurable per-cycle costs

Standing charges should normally be excluded because running a cycle does not
change them.

This broader cost model will be particularly relevant when evaluating negative
electricity prices. Consuming electricity may appear profitable while still
incurring water, consumable, and equipment costs.

## Retirement Plan

Legacy helper names should remain only long enough to migrate state forward.
After the new model is validated:

- legacy scripts should be removed
- legacy dashboards should be replaced or archived
- legacy helper entities should be deleted
