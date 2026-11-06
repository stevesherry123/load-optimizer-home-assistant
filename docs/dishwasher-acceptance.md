# Dishwasher candidate acceptance walkthrough

This walkthrough covers the selected first feature release: overnight requests,
operating costs and household controls. It is a plan for collecting evidence,
not a record that the physical or human checks have passed. Installation and
device operation require a separately agreed supervised trial.

## Prepare the trial

1. Record the exact candidate commit, HA version and appliance integration version.
   Use a separate test installation for setup and restore checks. Do not connect
   two active controllers to the same dishwasher.
2. Preserve a restorable HA backup and the previously installed release reference.
   Complete active washes and learning captures before changing code. Record and
   cancel pending requests that must not survive the change.
3. Follow [setup](getting-started.md) and [Home Connect control](dishwasher-control.md).
   Keep Schedule After Loading and Profitable Extra Runs off initially. Controller
   activation and a one-wash request are separate actions.
4. Verify programme names, eligible policy, W/kWh units, timestamped future prices
   and tariff timezone. A current unit price alone cannot price a whole cycle.
   Verify at least one completed learned cycle before trusting a recommendation.
5. Review [operating costs](operating-costs.md). Record household estimates and
   any deliberately unconfigured zero assumptions. Never count the same expense
   in both fixed and consumables costs.

## Check the household controls

Perform this with an unfamiliar tester where possible, on desktop and phone.
Record actual device/browser and viewport; template rendering is not visual proof.

| Task | Expected outcome |
| --- | --- |
| Find the next-wash card | Permission, timing, programme and any blocker are understandable. |
| Set Overnight Start and Dishes Ready By | Times are readable and use tariff-local time; new defaults are 21:00–07:00. |
| Request one overnight wash | A queued request is distinct from confirmed washing; optional door mode remains off. |
| Inspect a late-finish explanation | The proposed start is inside the original window; later completion is explicit. |
| Cancel the pending request | The pending wash clears. Cancellation does not claim to stop a running wash. |
| Find cost details | Electricity and other costs are separate; missing configured costs are disclosed. |
| Find optional modes | Door scheduling and profitable extras are separately labelled and remain off unless deliberately enabled. |

Check missing entities, clipped labels, unreadable times, scrolling and whether
actions are easy to distinguish. Record help the tester needed, not only whether
they eventually completed a task. Keep customised dashboard copies separate from
the shipped template.

## Supervised physical run

Use a normally loaded dishwasher with its manufacturer controls available. Agree
the trial window in advance so someone can observe the start; do not enable extra
runs just to generate a test. Retain connection, door and remote-start interlocks.

1. With optional modes off, explicitly request one wash. Record the original
   authorised start window, selected programme, estimated start/finish and costs.
2. Verify the actual start occurs inside that window and that appliance feedback
   confirms washing. A sent command or a queued card alone is insufficient.
3. Observe completion, learned-run count and recorded outcome. Record actual
   duration/energy and explain material differences from the estimate.
4. Confirm later refreshes do not create another wash. Inspect pending permission
   and history before leaving the system unattended.

Use the isolated automated fixtures for missing prices, closed-window dispatch,
ambiguous commands and telemetry loss. Do not deliberately disconnect household
services or interrupt an active wash to reproduce those failures. A live
late-finishing fallback need only be accepted if suitable conditions occur; retain
the automated evidence and mark any unobserved physical case as unobserved.

## Restart, installation and rollback

On the separate test installation, follow setup from a blank configuration and
confirm learning, a priced recommendation and registered controls without copying
the maintainer's private data. Record any undocumented step.

The isolated `tests/ha_dishwasher_restore_smoke.py` writes the real HA Store file
and copies it into fresh temporary configurations. It verifies the original
authorised window, next-request time setting and programme options survive;
cancelled and expired requests stay cleared after another restore. No device
service is permitted. This covers scheduling storage for this candidate, not a
full HA backup, learned-profile recovery or compatibility with an older release.

Test a queued-request restart with mocked device commands before a physical
restart trial. A real restart needs an agreed maintenance window, no active wash
or capture, and someone able to supervise a retained request when its window opens.
Record the same request/window surviving, with no duplicate start.

Before rollback, turn optional modes off, cancel pending requests and finish any
active appliance work. Restore the backup matching the prior release if older
code cannot read newer stored state. Verify settings, learned profiles, controls
and absence of unwanted requests after restoration. Reinstalling old code alone
does not establish data recovery.

## Record outcomes

Keep raw household evidence and backups private. Share only redacted findings.
For each case record:

| Field | Value to record |
| --- | --- |
| Candidate and environment | Exact commit, HA/provider versions; device/browser for UI cases. |
| Case | Setup, controls, physical run, restart or rollback. |
| Expected and observed | Include local timezone, original window and actual outcome where relevant. |
| Evidence | Private log/screenshot reference or automated run link; no tokens or household identifiers. |
| Result | Pass, fail or not performed; reason and follow-up owner. |

Leave unperformed gates open in the [release record](release-readiness.md).
Fix failures, validate the changed candidate and repeat affected acceptance before
promotion. No version bump, deployment or publication follows automatically.
