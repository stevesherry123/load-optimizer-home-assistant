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
  E --> A[Optional HA automation]
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
2. The app samples the appliance and detects cycle start and finish.
3. Completed cycles become learned programme models containing runtime, energy,
   confidence, and a representative power profile.
4. The provider layer normalizes tariff periods and optional green, blocked,
   deadline, solar, or battery context.
5. The optimiser overlays each learned power profile on each candidate tariff
   window and calculates energy and operating cost.
6. Policy and safety constraints remove ineligible candidates.
7. The remaining candidates are ranked and published as recommendations.
8. Optional Home Assistant automations queue and execute a request.
9. Execution is confirmed from appliance state; request, confirmation, failure,
   and queue-cancellation events are recorded separately.

## Automatic execution decision tree

~~~mermaid
flowchart TD
  T[Scheduler tick or request change] --> Q{Automatic request queued?}
  Q -- No --> W[Wait]
  Q -- Yes --> D{Is the request due?}
  D -- No --> V{Has the recommendation changed materially?}
  V -- Yes --> C[Cancel queue and publish reason]
  V -- No --> W
  D -- Yes --> S{Is the request still within the start-lag safety window?}
  S -- No --> X[Expire request and notify missed start]
  S -- Yes --> I{Is the appliance idle?}
  I -- No --> B[Block and report active cycle]
  I -- Yes --> R{Is remote execution safe?}
  R -- No --> B2[Block and report readiness reason]
  R -- Yes --> G{Normal run needs a fresh door opening?}
  G -- No --> P[Power on if configured, select programme, send start]
  G -- Yes --> H{Door opened since previous cycle?}
  H -- No --> B3[Block and request door opening]
  H -- Yes --> P
  P --> K{Appliance confirms running?}
  K -- Yes --> Y[Record confirmed start]
  K -- No --> N[Record failed start with state diagnostics]
  Y --> L[Monitor cycle and learn profile]
  N --> Z[Notify and optionally block programme for retry]
~~~

The queued plan is revalidated before its due time. Once due, the captured
programme and start time are preserved for execution, subject to safety and
staleness checks. A later recommendation refresh must not silently replace a
due request.

## Safety gates

Automatic execution must pass all applicable gates:

- recommendation and programme policy allow the run
- confidence meets the configured threshold
- the appliance is idle
- Home Connect is connected
- remote control and remote start are enabled
- the door requirement is satisfied
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
