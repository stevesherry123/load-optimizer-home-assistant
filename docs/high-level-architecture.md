# Load Optimizer: High-Level Architecture

This document describes the application for users, contributors, and
integration authors. It deliberately stays above implementation detail.

## System shape

~~~mermaid
flowchart LR
  HA[Home Assistant] --> S[Source entities]
  S --> P[Provider normalisation]
  S --> D[Device adapter]
  D --> L[Cycle learner]
  L --> M[Programme models]
  P --> O[Optimiser]
  M --> O
  O --> R[Recommendations]
  R --> E[Execution safety layer]
  E --> A[Native request and execution controller]
  A --> HC[Appliance adapter / Home Connect]
  HC --> F[Confirmed cycle]
  F --> L
  R --> UI[Dashboard and notifications]
  E --> UI
~~~

The optimiser is device- and provider-agnostic. Home Assistant supplies the
entities and orchestration; the core consumes normalized prices, constraints,
windows, and learned programme models.

## Main data flow

1. Home Assistant exposes power, energy, programme, appliance state, tariff,
   calendar, and optional local-energy entities.
2. The integration samples the appliance and detects cycle start and finish.
3. Completed cycles become learned programme models containing runtime, energy,
   confidence, and a representative power profile.
4. The provider layer normalizes tariff periods and optional green, blocked,
   deadline, solar, or battery context.
5. The optimiser overlays each learned power profile on each candidate tariff
   window and calculates energy and operating cost.
6. Policy and safety constraints remove ineligible candidates.
7. The remaining candidates are ranked and published as recommendations.
8. The optionally activated native controller persists and executes authorised requests; external scripts can request or cancel a wash.
9. Execution is confirmed from appliance state; request, confirmation, failure,
   and queue-cancellation events are recorded separately.

## Development normal-wash request flow

The unreleased overnight scheduling work separates permission from a priced plan:

~~~mermaid
flowchart TD
  R[Explicit request or opted-in door rule] --> P[Persist permission and original start window]
  P --> T{Complete price coverage and eligible programmes?}
  T -- No --> N[Notify and wait inside original window]
  N --> T
  T -- Yes --> F{Any cycle finishes inside window?}
  F -- Yes --> C[Choose cheapest fitting cycle]
  F -- No --> L[Choose cheapest cycle starting inside window]
  C --> Q[Persist and reassess plan]
  L --> Q
  Q --> D{Due inside original start window?}
  D -- No --> W[Wait or expire when window closes]
  D -- Yes --> S[Recheck prices, authority and physical safety]
  S --> X[Send commands and confirm appliance start]
  X --> M[Monitor outcome and learn]
~~~

New default windows are 21:00–07:00 in the configured tariff timezone. Explicit
YAML windows are retained; native time controls override defaults for subsequent
requests. Fallback cycles may finish late, but cannot start outside the window.
Cancelling or expiring permission prevents later price recovery from reviving it.
Normal requests take priority over opportunistic extra runs.

A valid queued plan follows revisions until two minutes before its saved start.
Missing or invalid prices pause execution, including during the freeze. The
controller checks the original window again before each start-command path.
Existing manual programme overrides retain their explicit programme/time behaviour.

## Safety gates

Automatic execution must pass all applicable gates:

- recommendation and programme policy allow the run
- confidence meets the configured threshold
- the appliance is idle
- Home Connect is connected
- remote control and remote start are enabled
- the physical door is closed; optional door-based authorisation is satisfied for automatic normal requests
- the programme is selectable
- negative-price runs fit the power-hungry portion inside the eligible window
- the request has not exceeded its maximum start lag

Power-off is treated as a warning when the configured engine can safely power
the appliance on. It is a blocker when that capability is unavailable.

## Cost and profile model

Each candidate start uses the learned representative power profile, not merely
total kWh multiplied by an average price. The profile is split into time
segments and overlaid on tariff periods. This captures the cost of heating
phases landing in different price slots.

If a programme lacks a sufficiently reliable profile, the app falls back to a
less precise estimate and exposes the confidence and data source.

## State and observability

The system publishes separate concepts:

- recommendation state and candidate details
- schedule and traffic-light readiness
- execution lifecycle: ready, starting, running, completed, or failed
- start request audit
- appliance confirmation audit
- command diagnostics
- queue cancellation reason
- recent manual and automatic run history

This separation is intentional: a queued request, an appliance-confirmed start,
and a later queue cancellation are different events and must not overwrite one
another.

## Failure handling

Failures are visible at the layer where they occur:

- **Data failure:** tariff, calendar, or sensor data unavailable
- **Eligibility failure:** no programme or window satisfies policy
- **Safety failure:** appliance or door state is unsafe
- **Command failure:** Home Assistant/Home Connect cannot send the command
- **Confirmation failure:** command was sent but running state was not observed
- **Runtime failure:** an active cycle stops unexpectedly

Each failure should retain its timestamp, programme, mode, relevant appliance
state, and reason. Recovery and retry remain opt-in and safety-gated.

## Extension points

Future provider layers can add calendar deadlines, carbon intensity, solar, or
battery state without changing the core optimiser. Future device adapters can
support washing machines, EVs, immersion heaters, or other flexible loads as
long as they provide the shared concepts: cycle detection, programme model,
runtime, energy, and execution state.
