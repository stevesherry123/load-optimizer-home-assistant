# Experimental EV Control

Development branch: `feature/ev-charger-control`, isolated in its own checkout.
Not released or approved for unsupervised use. An explicitly approved owner-only
small-load trial was installed on 19 October 2026; the real EV entry was not
reconfigured. Stable and other beta development remain independent; this RPi
uses a private overlay on beta.9, which a later HACS update can replace.
No production charger commands
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
  meter progress after the configured grace period. Meter resets stop owned
  charging and disarm the controller. A large battery-gain shortfall is advisory:
  it appears in delivery feedback and the dashboard without cutting power.

Delivery comparison uses metered wall energy times the assumed charger
efficiency divided by battery capacity. It tolerates at least five percentage
points of SOC delay/quantisation, plus the configured relative tolerance.
This is discrepancy detection, not proof of battery health, usable capacity,
or charge retention after driving or disconnecting.

## Read-Only Dashboard And Offline Review

This branch adds native **Charging Review** and **Charging Chart Horizon**
sensors, plus an optional [EV dashboard template](dashboard.md#experimental-ev-review).
They show battery inputs, tariff and selected slots, remaining wall energy,
estimated cost/finish, actual power/meter readings, ownership, last stop reason
and source freshness. The dashboard has no charger-control actions.
The owner trial has a separate test dashboard using simulated battery inputs;
the private real-EV household mapping has not been applied.

For review without Home Assistant or a physical plug:

```sh
python dev/ev_replay.py --output .local/ev-review.html --json-output .local/ev-replay.json
```

Open the generated HTML directly; no development server is required. It contains
fictional data and blocks network connections with a content-security policy.
Use Next Step or the timeline slider to inspect the actual planner, controller
and delivery monitor against fake state/service objects. The normal scenario
needs six charging hours within twelve hours of negative prices and alternates
selected and excluded half-hours. Other scenarios exercise no charging,
a stalled meter, disconnection and a stale plan. The chart retains the initial
plan for comparison; the table shows the remaining plan at each step.

Delivery totals span separate charging bursts in the same enabled session;
each new burst has its own confirmation grace period. Continued meter progress
is checked after initial confirmation, and final totals/stop reason remain visible
when charging ends. A new enable resets the session. This replay verifies logic,
not real command timing, charging taper, telemetry cadence or physical compatibility.

## Owner Mapping

### Small-Load Test Bench

`dev/ev-test-package.yaml` provides explicitly simulated battery percentage,
capacity, target and connection helpers, bridged to sensor inputs for a separate
EV entry. `dev/ev-test-dashboard.yaml` exposes these controls alongside the real
socket/meter and automatic-control switch. Replace the generic load source IDs
with a confirmed test socket and its measured power and cumulative energy source;
never attach this package to the car entry. Merge the EV review cards into this
test dashboard using the new entry's actual sensor IDs.

The example's 0.6 kWh capacity is fictional, not the laptop's battery specification.
Use an explicitly assumed or measured expected power (for example 0.06 kW = 60 W),
not an EV-sized power value. Small loads down to 1 W are valid planner inputs.
The example connection resets off on restart, and the controller remains off.
Enabling control requires the real socket to be off first; existing manual-on
power is never adopted. No dashboard installation should toggle the socket.

Move the simulated battery slider to model charging progress. Its periodically
refreshed sensor is a declared synthetic input, not evidence of real battery
health. Real power and energy checks are not bypassed. If the slider does not
increase as measured energy predicts, the existing shortfall protection stops
owned charging; a full laptop drawing too little power also fails confirmation.
The template's charging status is inferred from real socket power, not a vehicle
API. Prefer a lifetime energy meter; a daily/monthly meter resetting during a
trial deliberately fails closed. Review thresholds and keep trials supervised.

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

## Owner Trial Acceptance: 19 October 2026

Installed runtime commit `e34441c2604b1eec949ad0b59f2e6fedb9512418` directly
from this branch, with dashboard-only polish from `869229d`. No tag, GitHub
release, main merge or HACS distribution was created. The version label remains
the existing beta.9; `_owner_trial_build.json` records the exact owner build.
Only one integration-source rollback copy was retained; HA configuration stores
and learned data were not replaced. The configuration check and all five CI
jobs passed before one idle-time restart.

A separate **Charging Test Bench** entry uses real current/next-day tariffs and
the confirmed small-load socket's power/monthly-energy readings, with a fictional
0.6 kWh battery and assumed 60 W expected charging power. Automatic control was
left off. Live helper tests moved battery charge 20 -> 100 -> 20: the plan cleared
at target and rebuilt on restoring the deficit. No physical switch commands were
sent. This is not a physical charging or stop-acknowledgement acceptance.

Verified the existing 222 entity identities, both original dashboards, learning
counts and queued dishwasher request. The washing-machine count included a cycle
completed before deployment, not a restart-generated run. No current integration
errors were logged. Household mappings and the detailed verification report are
private, ignored local files. The test dashboard is available at
`/charging-test-bench/charging-test`; existing dashboards remain independent.

## Passive Test Alerts

`dev/ev-test-alerts.yaml` adds optional command-context capture and state-change
notification observers for the confirmed test socket. Their only actions write
test metadata or send notifications; they cannot switch a load. The owner trial
has these enabled for HA and the explicitly chosen phone, with a **Switch alerts**
dashboard toggle. Installing them did not restart HA or alter charging controls.

Messages include old/new state, home-local time, a matching HA service command
when its context and timestamp agree, and the controller's latest reported reason.
That reason is diagnostic context, not proof of who caused an external change.
Unknown callers and availability/recovery changes are labelled explicitly.
Attribute-only updates and initial entity creation do not generate relay alerts.
The hidden command helper is generated metadata, not a user-editable setting.

Isolated HA acceptance uses a synthetic switch and fake destinations to test
service/user contexts, unknown changes, availability, attribute filtering and
the disable toggle. Live setup sent a clearly labelled readiness notification
to each destination; it did not toggle the actual socket to test the observers.
Physical transition delivery still needs observation during the owner's trial.

The battery slider is manual by default. Optional `dev/ev-test-battery-fill.yaml`
adds a clearly labelled, default-off simulation toggle. Import its helper and
automation and replace the load, meter and controller placeholders. Add
`input_boolean.ev_trial_simulate_battery_gain` to the test dashboard to expose it.
While connected, controlled charging is active, and the socket is on, this
simulation advances the helper by measured kWh divided by simulated capacity,
assuming 100% test efficiency. It rejects unavailable/reset meters, wrong units
and jumps over 5% of capacity per update, and clamps the helper to 100%.
This is synthetic feedback derived from the same meter: it does not independently
validate battery gain or measure the laptop's real battery. Switch it off to
exercise manual SOC changes or the battery-gain-shortfall warning.

The planner now allocates only the required energy in its marginal slot. It no
longer rounds a paid slot up and later prunes a current partial slot; that
interaction caused repeated mid-slot OFF / next-boundary ON transitions. The
three-hour controller replay replans every 30 seconds and asserts exactly two
charging bursts, no extra commands, metered progress and a target-reached stop.
This is continuous energy/cost allocation, not a global appliance wear optimizer;
configurable minimum dwell and competing external schedules remain future work.

Keep simulated SOC consistent with the meter or expect a delivery-shortfall warning.
The warning clears when the reading catches up. It does not bypass selected-slot
boundaries, the target, missing/stale telemetry, charging faults or meter checks.
An already-on manual session remains unowned; switch the test socket off before
explicitly enabling control. Without a ready-by deadline, newly published prices
can move the remaining plan into a later day. Neither observer changes that logic.

## Refinement And Deployment Gates

### Bounded Sessions And Restart-Safe Test Inputs

The development controller exposes `ev_session_max_hours` (default 24 hours)
and `ev_session_max_energy_kwh` (default 120 kWh) in setup/options. Choose much
smaller allowances for the laptop trial, for example 4 hours and 0.3 kWh; these
examples are not automatically installed settings. Duration includes waiting,
not just socket-on time. Energy is the selected supply meter's increase since
explicit enabling, including any consumption during slot gaps. Use a dedicated
charger meter; unrelated loads will conservatively consume the allowance.

Replanning, battery changes and slot gaps do not reset either budget. Exhaustion
stops only an owned socket and disarms the controller. A new explicit enable
begins a new budget. Restart still disarms and does not silently resume. Meter
resets and missing/stale feedback remain blocking. Checks occur every ten
seconds and depend on meter reporting; this is not a hardware energy limiter.

Test battery, capacity, target and connection helpers now restore their saved
values instead of imposing startup defaults. On a new installation, configure
them before starting a test. Automatic control and battery-fill simulation do
not automatically enable after restarting.

Install `dev/ev-test-battery-fill.yaml` alongside the test package to expose an
explicit simulation-expiry date/time and `sensor.ev_trial_battery_simulation_status`.
Set a future expiry and explicitly enable simulation for a supervised session.
The status is `active`, `disabled`, `expired` or `expiry_not_configured`;
an expired/missing deadline prevents battery updates even if the toggle is on.
No hard-coded calendar date is required. When replacing an older privately
installed automation, remove its old additional one-day condition through the
supported automation editor; merely replacing the package cannot update a
separately stored automation. Preserve the current helper values during rollout.

Optional test observers now report decision transitions and the rising edge of
a battery-gain warning to HA and the selected mobile target. A continuing warning
does not notify on every meter update. These observers never command a socket;
they remain separately installed test assets, not automatic public notifications.

### Owner Laptop Safety Smoke, 20 October 2026

Tested the owner-only overlay with planner patch `009843f`, real socket feedback
and explicitly simulated battery/connection inputs. The real EV was not used.
Five deliberate ON/OFF pairs were confirmed in Home Assistant history:

| Scenario | Observed Result |
| --- | --- |
| Simulated SOC raised to 100% while charging | OFF in about 6 seconds; `target_reached`; no restart on refresh |
| Manual socket OFF while owned | Control disarmed in about 5 seconds; no automatic restart |
| Simulated disconnection | OFF in about 4 seconds; `vehicle_not_connected` |
| Simulated connection feedback unavailable | OFF in about 6 seconds; `telemetry_unavailable` |
| Graceful HA restart during owned charging | Socket OFF during shutdown; control remained disarmed after boot |

The disconnection and unavailable-feedback blocks pause charging without
disarming the opt-in switch: restored valid inputs can resume a selected slot.
Manual OFF disarms it. Restart also disarms it. This live check did not simulate
an abrupt power cut or an actual charger/vehicle communication failure.

After testing, restored simulated battery 98%, target 100%, capacity 0.6 kWh and
connection ON, with the socket, automatic control and battery-fill simulation OFF.
Alerts and the existing midnight cutoff were retained. No release/main merge.

Diagnostic follow-up: retain the manual-stop cause across later disabled ticks;
the current generic `disabled` state can obscure that successful safety action.

### Remaining Gates

1. Pass planner/control/monitor unit tests and real minimum-HA synthetic
   configuration, service and ownership-journal acceptance; no physical devices.
2. Review charger suitability for interruption, power-loss behaviour, competing
   manufacturer schedules, source update cadence, command latency and ownership.
3. Add a full-entry persisted reload/restart/failure test, configurable command
   dwell/backoff and notification guidance. The read-only review dashboard and
   isolated normal/fault replay are implemented, not physically accepted.
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
