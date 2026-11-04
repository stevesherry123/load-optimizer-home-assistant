# Installation and acceptance checklist

Begin with recommendations. Device control is a separate, deliberate step.
Use the notes for the exact installed release: this branch contains unreleased
overnight scheduling, total-cost and optional EV control work. A local test pass
does not publish or install it. The stable README and the development guides
describe different scopes until an accepted release includes these changes.

## 1. Record the installation

- Record the Load Optimizer version, Home Assistant version and supplier/device
  integration versions. Follow [Getting started](getting-started.md) for HACS
  installation; a downloaded update needs an HA restart to become active.
- Preserve a Home Assistant backup and the prior release reference before an
  update. Use a separate HA installation for development; two copies of this
  integration domain cannot run as independent stable and beta installations.
- Finish active dishwasher cycles and learning captures before an update or
  restart. Cancel pending requests if they should not survive the maintenance.
- Keep automatic appliance modes and EV Automatic Charging off while checking
  sources and configuring the first plan.

## 2. Check inputs before trusting a result

| Input | Acceptance |
| --- | --- |
| Appliance power and energy | Real W readings and cumulative kWh, with correctly converted units. |
| Future tariffs | Today/next-day rate attributes contain timestamped intervals; a current price alone is insufficient. Octopus value_inc_vat uses GBP/kWh. |
| Local time | Correct tariff timezone and daylight-saving behaviour; dashboard home-time display may use a different timezone. |
| Appliance programmes | Exact names from the appliance and an explicit eligible policy for each normal recommendation. |
| EV battery and capacity | Percentage, usable kWh, wall power in kW and efficiency as a fraction. Capacity is an entity reference, not a number entered as an entity ID. |
| EV connection and delivery | Dedicated cable status; a separate charger meter in W/kW for optional control. A powered switch, internet connection or idle car does not establish delivery. |

Missing sources are a reason to investigate, not to bypass the checks. Tomorrow's
unpublished prices can be empty while today's published slots remain useful.
The optimiser cannot assume unknown future electricity is free.

## 3. Prove appliance learning first

1. Follow the one-appliance example in [Getting started](getting-started.md), or
   the [Home Connect guide](dishwasher-control.md) for a fresh dishwasher hub.
2. Use the machine normally and allow the capture to complete. Confirm one new
   learned run, the expected programme and a plausible energy total.
3. Confirm a priced recommendation. Distinguish it from a queued wash request.
   Resolve no_eligible_programs through programme policy, not repeated washing.
4. Inspect the starter dashboard and relevant status explanations. Retain the
   existing appliance ID when editing; do not recreate IDs to change settings.

## 4. Accept optional dishwasher scheduling

Follow the controller activation and supervised manual test in the
[dishwasher guide](dishwasher-control.md). Do not enable automatic modes merely
to obtain a recommendation. Physical remote-start permission, connection, closed
door and supported programme checks remain necessary.

For the unreleased scheduling implementation:

- Check the configurable start window, default 21:00–07:00 local tariff time.
  Requesting an overnight wash grants one wash. Prefer a complete fit; a fallback
  can finish later but must start within that original window.
- Inspect expected start, finish and any late-finish explanation. Missing prices
  notify and retain permission only within the original window. Returned prices
  must not revive a cancelled or expired request.
- Verify cancellation clears the pending request without stopping a running
  wash. A second tick or restart must not duplicate a confirmed start.
- Leave Schedule After Loading off unless wanted. When enabled, the door-duration
  rule is a readiness heuristic; check the configured threshold, for example two
  minutes. It does not replace physical safety checks.
- Review [operating costs](operating-costs.md) before enabling Profitable Extra
  Runs. Omitted costs are visibly unconfigured zero assumptions; missing tariffs
  are never zero. Extras require positive total net benefit and cannot displace
  a requested normal wash.

## 5. Accept EV planning before optional control

The executable [EV form example](examples/ev-planning.yaml) contains generic
settings, not a configuration.yaml block. Replace its example entity IDs and
numeric assumptions using [the EV guide](ev-charging.md). Its required mode and
07:00 deadline are examples, not appropriate defaults for every household.

Confirm the selected mode, battery, target, projected level, price coverage and
shortfall. Required mode uses paid prices when needed and recommends useful
partial charging. Opportunistic mode respects its inclusive ceiling, defaulting
to free and negative prices; it does not guarantee the target.

Optional switch control uses [additional form fields](examples/ev-switch-control.yaml)
and [its own activation/recovery guide](ev-control.md). Saving must leave
Automatic Charging off. Verify suitability of power switching, real reporting
freshness, and the expected switch/meter/status delays before a supervised trial.
Check physical start and stop separately from sending commands.

During that trial, verify target completion, permission removal and a planned
interval end stop owned power. Keep the charger manufacturer's controls available.
Do not deliberately break live hardware or pricing to repeat synthetic failure
tests. A normal HA reload turns permission off and requires explicit stopped-state
reconciliation; a crash or unavailable switch can leave physical power unresolved.
Never treat an automatically created command as proof of charging or stopping.

## 6. Keep update and rollback evidence

Record the installed release, configuration assumptions and the actual supervised
outcome. For a rollback, first verify EV power is stopped using working charger
controls, leave automatic modes off, cancel pending requests and finish active
appliance captures. Preserve the current backup before restoring any older data.
Use the backup matching the older release if its storage schema cannot read newer
state. Merely downloading older code does not establish a safe data rollback.

For public promotion, follow [release readiness](release-readiness.md). Isolated
tests, human onboarding, physical acceptance, deployment and publication are
separate evidence. Any missing gate remains pending; do not label it passed.
