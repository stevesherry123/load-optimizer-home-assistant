# Dishwasher deadline consistency and pre-command recovery

The planner previously ignored an expired travel deadline while the command-time
adapter still enforced its raw helper value. A wash could therefore be queued,
rejected before any device command, and consume the night's reservation.

Planning and execution now share `legacy.app_runtime.schedule_constraints`.
A deadline older than the wash permission is stale. A deadline applicable to an
existing permission remains binding after it passes. The scheduler saves the
applicable deadline with that permission; clearing or extending the source helper
does not loosen the saved limit. A newly earlier deadline tightens it. Unreadable
configured constraints pause planning and execution instead of becoming no limit.
Expired applicable permissions require a fresh request.

A constraint failure before any device command retains the original permission
and its start-window boundaries. Recovery requires a new planner report and all
normal policy, confidence, physical readiness and tariff checks. A cached plan
cannot immediately retry. The existing window expiry still applies. A failure
once the command sequence has begun does not restore permission; uncertain start
and restart protection remain in force.

No automatic clearing of calendar helpers is needed for correctness. Existing
saved requests migrate without changing entity identities or learned profiles.
This patch does not change programme selection, power learning or cost estimation.

Regression coverage includes stale/future/unreadable constraints, timezone
conversion, persistence of applicable deadlines, expiry, recovery inside the same
window and refusal to recover after commands. The real Home Assistant overnight
acceptance test checks planner/adapter agreement and missing-constraint handling
without calling any appliance services.
