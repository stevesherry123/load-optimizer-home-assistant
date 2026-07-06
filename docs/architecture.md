# Architecture

## Overview

Load Optimizer is a Home Assistant App split into three layers:

1. Core learning and optimisation logic
2. Device adapters
3. Home Assistant API and dashboard surfaces

The core must not depend on Bosch, Home Connect, a particular washing machine,
or any other single appliance.

## Core Responsibilities

- Detect when a cycle starts and ends.
- Sample power throughout the cycle.
- Build and maintain learned cycle profiles.
- Estimate future runtime, energy, and cost.
- Select economical programs and start windows.

## Device Adapter Responsibilities

Each configured instance adapter should:

- read user-selected Home Assistant entities
- normalize program names and operating states
- determine whether a cycle is active
- map device-specific readings into the shared model
- avoid leaking manufacturer-specific concepts into the core

## Home Assistant Surface

Supervisor supplies the App with a temporary Home Assistant credential. The App
uses it to read configured source entities and publish stable status,
recommendation, and control entities.

The App owns persistence in its private `/data` directory. Home Assistant
entities are a public surface, not the primary database.

## Canonical Naming

The first configured instance uses the `load_optimizer_1_*` namespace. Later
instances use `load_optimizer_2_*`, `load_optimizer_3_*`, and so on, regardless
of appliance type or replacement history.

Examples:

- `sensor.load_optimizer_1_cycle_state`
- `sensor.load_optimizer_1_expected_runtime`
- `sensor.load_optimizer_1_expected_energy`
- `sensor.load_optimizer_1_recommendation`

## Data Flow

1. Adapter reads the configured Home Assistant source entities.
2. Core decides whether the instance is idle, active, or finishing.
3. Core stores sampled power in the private instance database.
4. Core updates learned statistics when the cycle finishes.
5. Optimizer combines learned profiles with tariff forecasts.
6. App publishes useful state and recommendations to Home Assistant.

## Persistence

Versioned JSON under `/data` is the initial persistence format. Writes are
atomic, and future schema changes must provide migrations.

## Legacy Retirement

A future migration tool will read legacy helper values through the Home
Assistant API and import them into the App database. Legacy scripts, dashboards,
and helpers can be retired only after the imported data and new runtime have
been validated.
