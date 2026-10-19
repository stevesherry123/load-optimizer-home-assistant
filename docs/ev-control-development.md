# Experimental EV Control

Development branch: `feature/ev-charger-control`, isolated in its own checkout.
Not released, installed or approved for unsupervised use. Stable and the
existing beta deployment remain independent. No production charger commands
are part of development acceptance.

## First Implementation

- Select a charger switch per EV entry; no household entity is hard-coded.
- Existing battery percentage, capacity, target, charge-power estimate,
  efficiency and ready-by settings remain planner inputs. Additional future-rate
  entities can supply current/next-day prices rather than a current-price sensor.
- Optional control adds power feedback, cumulative energy, vehicle charging
  status, maximum telemetry age, minimum confirmed power, confirmation timeout
  and delivery-shortfall tolerance. W/kW and Wh/kWh are explicitly normalised.
- Configuring these inputs creates an Automatic Charging Control switch,
  initially off. No switch is added for unchanged advisory-only entries.
- The plan refreshes every 30 seconds when a charger target is configured;
  control checks run every ten seconds. Mid-slot plans account for remaining
  energy instead of dropping the current half-hour on every refresh.
- The planner selects the cheapest nonconsecutive intervals to meet the
  required wall energy. Duplicate intervals do not create fictitious capacity;
  conflicting overlaps block the plan. Missing prices are not invented.
- Starts require a fresh complete plan, explicit connected state, valid battery
  inputs, available switch and fresh power/energy/charging-status feedback.
- Only owned charging is stopped outside selected slots, at target, on stale
  data, disconnection or feedback faults. Already-on manual charging is not
  adopted. A manual stop disarms automation rather than fighting the user.
- A journal records intent before energising. Restart/reload deliberately
  disarms automatic control and attempts to stop any journalled owned session;
  it does not silently resume. Failed stops retain ownership for retry/recovery.
- Charging confirmation requires meaningful power, vehicle charging status and
  meter progress after the configured grace period. Meter resets and a large
  battery-gain shortfall stop owned charging and disarm the controller.

Delivery comparison uses metered wall energy times the assumed charger
efficiency divided by battery capacity. It tolerates at least five percentage
points of SOC delay/quantisation, plus the configured relative tolerance.
This is discrepancy detection, not proof of battery health, usable capacity,
or charge retention after driving or disconnecting.

## Owner Mapping

A read-only entity audit found all required input roles. The proposed household
mapping is stored privately in the ignored `.local/ev-proposed-settings.json`,
not published in Git. The plug and local metering were unavailable, vehicle
connection was disconnected and no live control was attempted. The current
advisory entry uses a current-rate entity rather than forecast rates, and its
connection reference points at charging status. The private profile corrects
both references without changing the live entry.

Reported battery capacity is available as an entity; do not replace it with an
assumed model specification. Its usable-versus-nominal meaning and expected wall
charging power still require confirmation. Zero/offline power cannot establish
normal charging speed. Do not bypass missing telemetry to get a trial running.

## Refinement And Deployment Gates

1. Pass planner/control/monitor unit tests and real minimum-HA synthetic
   configuration, service and ownership-journal acceptance; no physical devices.
2. Review charger suitability for interruption, power-loss behaviour, competing
   manufacturer schedules, source update cadence, command latency and ownership.
3. Add a full-entry persisted reload/restart/failure test, configurable command
   dwell/backoff and explicit dashboard readiness/notification guidance.
4. Restore the owner's plug and fresh telemetry; confirm wall power, capacity
   assumptions and telemetry thresholds. Preview the full 12-hour/6-hour schedule.
5. Agree an owner-only test installation/selected commit and obtain explicit
   approval for installation and supervised physical switching. A dedicated
   branch is not a separate HACS release channel: a published EV prerelease can
   be offered to unrelated prerelease users, so do not publish one implicitly.
   Verify actual power, energy and SOC change,
   missed acknowledgements, loss of data and manual intervention.
6. Observe repeat sessions and only then separately approve stable promotion.

The current first slice is a refinement prototype, not a completed physical
charger acceptance or permission to alter the owner's installation.
It does not yet inherit learned-appliance Power Up calendar overlays or provide
a battery-health/parked-retention diagnosis. These need separately tested design.
