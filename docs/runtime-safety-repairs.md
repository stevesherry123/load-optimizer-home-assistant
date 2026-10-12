# Runtime Safety Repairs

Status: reviewed, unreleased work on `fix/runtime-data-safety`, 12 October 2026.
Based on main plus the existing onboarding documentation and validation commits
(`becd204`, `31c87e6`). No tariff-beta feature or negative-run scheduling fix was
merged incidentally. The owner approved pushing this branch and opening a review
request in this repository only. Merge, version changes, release and deployment
remain separate approvals. No live HA access or physical appliance command was
performed for this stage; the HACS catalogue submission is unchanged.

## Approved Repair Scope

| Review item | Local implementation |
| --- | --- |
| R1: missing power completes a capture | Missing/unknown/unavailable, negative, boolean and non-finite power are not measured low power. No missing sample is appended and the finish debounce resets. |
| R2: textual false becomes permission | Retains the existing fail-closed conversion from the onboarding validation commit. No automatic opt-in is enabled. |
| R3: missing mandatory no-run source permits scheduling | Configured feeds must be readable. Valid empty feeds pass; missing entities, unavailable states, calendar failures and malformed event contracts block. Every configured source must pass. |
| R4: unsafe configuration saving | Retains bounded parsing, duplicate detection, source review and active-capture/pending-request edit guards. Repairs validation of existing comma-separated green/no-run sources. |

## Review Follow-Up

The review reproduced and repaired two additional gaps:

- Optimisation, publishing, dishwasher control and benchmark saves could bypass
  the appliance-source guard and reload the learned hub during active work.
  Every learned-hub settings section now defers a known capture or queued start,
  retains submitted values and leaves options, requests and registered identities
  unchanged. EV benchmark settings remain independent.
- The source review treated comma-separated window references as a single entity.
  It now checks each source separately and reports only genuinely missing inputs.

Real minimum-HA onboarding tests reproduce both failures against the old code
and verify the repairs for the generic and Home Connect examples. Captures and
queued requests in these tests are synthetic; no real command is sent.

## Capture Recovery

An outage retains the capture identity and last valid samples. It publishes
`source_unavailable` with `health_status: power_source_unavailable`. Missing
reads do not grow the stored profile. After 30 minutes of an ongoing outage,
the status attributes also report `attention_required: true`.

There is deliberately no timer that declares an unobserved cycle complete.
Recovery at high power resumes the same capture; genuine low-power readings
restart the normal debounce. An explicit appliance terminal state can still
end it. Any capture with an observed power gap is excluded from learning with
`power_source_gap_during_cycle`; its energy is not estimated by interpolating
across the gap. A restart exclusion may take precedence if both occurred.
Existing counts, models and the last successfully learned cycle are untouched.
The gap marker survives storage/reload and is removed with the finished capture.

This conservative first repair excludes even a brief observed gap. A later
gap-tolerance policy would need its own evidence and approval. Existing active
power, finish-delay and washing-machine learning thresholds have not changed.
Unchanged valid readings are not declared stale solely because `last_changed`
is old; source freshness is not inferred from a successful optimizer scan.

## No-Run Enforcement

Price estimates can remain available, but recommendation/readiness signals are
blocked when a configured no-run source is unreadable. The reason is visible
even with detailed diagnostics disabled. Good-to-start, automation-ready and
active recommendation-window signals cannot falsely indicate permission.
Optional green-window failures remain advisory.

The native controller rechecks current sources before automatic power-on,
program selection, start and fallback commands. Calendar fetches have a
10-second timeout each and distinguish failure from a successful empty response.
Checks cover the whole expected cycle shifted to its actual start, including
bounded fetch latency. A newly overlapping no-run event blocks a saved plan.
All-day calendar dates use Home Assistant's timezone, not the viewer's timezone.

New requests record whether they are automatic. Pre-upgrade saved automatic and
negative-price requests are conservatively checked as automatic. Explicit manual
starts retain their previous behavior, including cooldown overrides and door,
connectivity and remote-control checks. This slice does not add a new no-run veto
to explicit manual commands. It does withhold engine recommendations when their
configured mandatory source is unreadable; manual control is not an assertion
that a no-run calendar has been checked successfully.

### Remaining Planning Boundary

The recommendation scan currently reads calendar windows only through the
configured search/forecast horizon, without adding the candidate's duration.
A candidate near that boundary can therefore look eligible despite a later
no-run event. The fresh automatic command-time check above covers the entire
actual cycle and blocks that start. Extending the planning fetch and filtering
range, with an end-of-horizon regression, remains a separate follow-up; these
repairs do not claim that every future recommendation is already complete.

## Local Acceptance

Against Home Assistant 2024.12.0 and Python 3.12:

- 276 unit tests pass, including outages, high/low recovery, explicit completion,
  exact existing-model/count preservation, multiple sources, failed/malformed
  fetches, new overlaps, all-day timezone and command/fallback checks.
- `ha_runtime_safety_smoke.py` passes using real config entries, storage,
  registered entities, reload and the coordinator-to-controller preflight wiring.
  It verifies no false count increment, preserved identity, source recovery and
  a fresh overlapping event without another scan. All device calls are guarded;
  no HTTP listener, test login, supplier or AI call is used.
- Existing platform/config-flow import, clean onboarding, dashboard templates,
  security/privacy and EV lifecycle checks pass. The EV lifecycle runner's
  optional localhost listener was denied by this sandbox; its backend flow,
  reload, registration and persistence assertions still passed. No new browser
  acceptance is claimed.
- Bandit reports no findings; the working-tree credential scan reports no leaks.
- An isolated idle-memory probe through stable v1.5.7 and back preserves the exact
  schema-v1 database, counts, models and last valid cycle. This is storage-format
  compatibility, not a full HACS/HA rollback deployment. Do not downgrade during
  a capture or pending request; old code does not enforce these new safeguards.

CI includes the new real-HA safety smoke test and the extended settings guards.
The repository review request is the authoritative record of remote CI,
including HACS validation and hassfest; local results alone do not imply those
checks passed. Human review, a separately approved release and supervised live
acceptance remain outstanding. R5's repeated negative-run fix and
comparable-integration feature decisions are separate next steps.
