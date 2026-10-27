# Runtime Safety

This describes the main-branch safety contract. Main may contain unreleased
improvements; match support expectations to your installed release's README and
changelog. These rules do not authorize appliance commands or change opt-ins.

## Capture and source failures

Missing, unknown, unavailable, negative or non-finite power is not a measured
low-power completion. Retain the capture identity and valid samples, publish
source health, and avoid growing the profile with fabricated readings.

Valid high-power recovery resumes capture; genuine low-power readings restart
the normal finish debounce. Explicit supported appliance terminal states can
still end a capture. A capture with an observed source gap is excluded from
learning rather than estimating energy across missing observations. A restart
exclusion may take precedence. Successfully learned counts/models remain intact.

Do not infer sensor freshness from a successful optimiser refresh or an old
`last_changed` value alone. Investigate source health through the appliance's
entities and redacted diagnostics.

## Automatic starts and calendars

Configured mandatory no-run feeds must be readable. A valid empty feed differs
from a missing entity, unavailable state, malformed response or failed request.
Check every configured source and the whole expected cycle, not just its start.
Optional greener-window failures remain advisory.

Before automatic power-on, programme selection, start or fallback commands,
revalidate current readiness and no-run evidence. All-day calendar dates follow
HA's home timezone, not the viewing browser. A newly overlapping event can block
a previously queued plan. Candidate start horizons do not justify ignoring a
restriction later in the expected cycle.

Manual cooldown overrides are not permission to bypass door, connectivity,
remote-control, ownership or supported-device safety checks. A recommendation
is not proof that a physical start occurred.

## State and maintenance

Keep settings edits from reloading a known active capture or queued start.
Serialize imports and scans; validate replacement data before changing memory.
An executor worker cannot be stopped merely by cancelling its awaiting task, so
finish its state/save work before allowing an import or reload to take ownership.

Maintenance outcomes use notifications or actionable service errors. If another
integration occupies an intended entity ID, Repairs explains the conflict; do
not delete that integration's entity automatically. Review obsolete package
definitions yourself before removing them, then reload Load Optimizer.

See [troubleshooting](troubleshooting.md), [migration](migration-addon-to-integration.md)
and [clean-install acceptance](onboarding-acceptance.md).
