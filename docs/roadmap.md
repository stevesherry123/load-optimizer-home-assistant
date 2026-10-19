# Roadmap

This roadmap is the canonical place for planned work, backlog ideas, and future
design notes. Keep released changes in `CHANGELOG.md` and keep
implementation architecture in `docs/architecture.md`.

## Near-Term Priorities

- Observe the next real Power Up and native delayed-start transition following
  the verified [beta.9 deployment](power-up-pricing.md#deployment-acceptance-19-october-2026).
  Permanent calendar pricing is configured and the expired manual override is
  disabled. Do not start a wash or restart merely to complete these observations.
- Repair optional blank entity-selector validation in appliance tariff settings.
  HA rejected the saved blank primary selector during the 19 October edit; using
  an existing tariff source allowed the reviewed change without altering the
  effective source pair or history. Show effective legacy calendar mappings in
  the source review so retired aliases do not produce misleading warnings.

- Observe repeated free-price washes before separately approved stable promotion.
  Automatic overnight completion and learning passed the 15 October live audit.
  Local unit and real-HA
  synthetic acceptance do not prove future appliance execution.
- follow up separately with guided appliance/policy editing,
  selectable control targets and generated dashboards; add privacy-safe screenshots,
  issue forms and an unfamiliar-user onboarding trial before broad promotion
- Add a separately designed confirmed-physical-cycle quota ledger, independent
  of learning rejection and recent-profile retention. Current finite-window
  limits count learned runs and conservatively pause when history is incomplete;
  do not present them as a lifetime record of every physical wash.
  The [ledger and guided-setup discussion draft](physical-cycle-ledger-design.md)
  is retained in `beta/next`, not implemented. Agree manual-cycle,
  failed-start and window-overlap accounting before shadow collection/enforcement.

- await maintainer review of [HACS submission #11744](https://github.com/hacs/default/pull/11744)
  for stable v1.5.7, submitted on the owner's behalf on 9 October. All upstream
  checks passed; respond to requested changes without duplicate requests or
  routine comments. Submission is not catalogue acceptance.
- Deploy and observe [published forecast coverage](forecast-coverage-plan.md)
  after separate release approval: the owner
  confirmed that a normal approximately 16:00 publication covers most of the
  next day, with the tail supplied later. Separate usable forecast analysis/AI
  readiness from complete-day storage; match historical comparison coverage and
  disclose the unknown tail. The beta.7 calendar-day gate was too strict for
  this pattern. The replacement shipped in beta.8 and is retained in beta.9;
  live partial analysis/date rollover passed. Tail/revision observation remains.
- Observe the constrained AI replacement after its verified beta.9 deployment.
  The first approved 17 October call misstated coverage and baseline warm-up.
  An additional authorized retest preserved facts but introduced unsupported
  demand speculation. The unreleased prose guard and authoritative facts prefix
  were superseded by constrained finding selection. The replacement renders all
  prose from local deterministic templates and passed one separately authorized
  real structured-provider replay on 17 October. The complete beta.9 code passed
  440 unit tests and all five CI jobs and was installed on 19 October. Further
  paid calls require fresh approval. Controlled stale-text replay passed;
  natural revision observation remains open. See
  [provider acceptance](forecast-coverage-acceptance.md).
- observe the combined beta through normal partial publication, later tail
  completion/revisions, date rollover and appliance cycles before separately
  approved stable promotion; imported history now satisfies warm-up
- implement effective-dated price-cap references and additive historical rebasing;
  retain raw comparisons and disclose missing references rather than guessing
- add a public Tariff Intelligence dashboard section for the new beta entities,
  with travel-timezone/mobile/DST tests before it enters stable
- retire Octopus Intelligence only after the accepted replacement features and
  provider tests pass; its mismatching cache and running app are still preserved
- continue decomposing the embedded compatibility engine behind stable native
  integration entities without changing migrated learning data
- add appliance-cycle load entries alongside the v1.0 EV charging load type
- add integration diagnostics and repairs for missing tariff or vehicle entities
- improve profile-weighted tariff cost estimation across half-hour slots
- extend helper-driven deadline support for calendar and travel-aware scheduling
- continue refining daytime and overnight scheduling windows
- expose a recommended-window active state for dashboards and automations
- add a manual recalculation service for tariff, policy, or test changes
- account for household solar generation and battery storage when estimating the
  effective cost of running a cycle
- add optional greener-window scheduling that compares the cheapest candidate
  with a lower-carbon or provider-highlighted green candidate

## Completed Recently

- Published and installed beta.9 from `cd7eed6` on 19 October with one idle-time
  restart. Configured permanent Power Up calendar pricing through the reviewed
  options flow and disabled the expired temporary override. Verified unchanged
  identities, devices, learning, both dashboards, tariff history and controls;
  calendar sources were readable and no current integration errors were logged.
  AI remains disabled. See [deployment acceptance](power-up-pricing.md#deployment-acceptance-19-october-2026).
  Later branch changes are not included in this release; main, stable v1.5.7
  and the upstream HACS submission are unchanged.

- Reviewed publication and scheduling explanations on 19 October. An unreleased
  follow-up distinguishes native delayed-start timers, shows automatic-only
  cooldown dates and translates pricing/source blockers in both templates.
  This does not modify control decisions or install a dashboard on the owner's
  instance. The read-only household audit is retained privately, not published.

- Published and installed beta.8 after owner approval. The 16 October audit
  verified preserved identities, learning, dashboards, history and queued wash;
  real partial-forecast analysis and the subsequent automatic wash passed.
  See [deployment acceptance](forecast-coverage-acceptance.md). The subsequent
  authorized structured-provider replay passed; stable remains v1.5.7.

- Implemented scoped partial-forecast analysis and manual narrative eligibility
  on `beta/next`, with matched historical intervals, DST handling and stale-text
  protection. All 418 unit tests and the new minimum-HA synthetic-provider
  acceptance pass. No provider charge, release or installation was performed.
- Verified the owner's actual beta.7 automatic overnight wash completed and
  incremented both total and programme learning; the queue cleared and the
  current integration log had no errors. Private household evidence stays local.

- Cleaned current contributor, tariff/import/AI and HACS guidance to use the
  single `beta/next` branch and installed beta.7, with older branch inventories
  and acceptance records explicitly dated as historical. Evening live checks
  reproduce the saved overnight choice and all one-to-four-hour generic windows.
  All published tomorrow rates match the official tariff API; the missing final
  hour prevents full-day classification and the manual AI test. No control,
  source settings, restart, release or upstream HACS change was made. Actual
  revision observation and the owner's promotion review remain. The subsequent
  15 October audit cleared the actual overnight wash gate.

- Consolidated development onto `beta/next`, retiring six superseded remote
  branches and replacing three reviews with draft PR #18. Published and
  installed v1.7.0-beta.7 with whole-night pricing and automatic-only overnight
  replanning after 396 unit tests, real minimum-HA acceptance and all five CI
  checks. One idle-time restart preserved learning, history, controls, identities
  and both dashboards. Runtime diagnostics and the current integration log pass;
  real future wash observation and stable promotion remain separate gates.
  See [overnight acceptance](overnight-planning-repair.md).

- Published and installed v1.7.0-beta.6 after 285 unit tests, isolated minimum-HA
  lifecycle/dashboard/security checks and all GitHub validation jobs passed.
  The planner no longer perpetually defers off-grid scans or ignores an active
  opportunity in favour of a cheaper future one. One restart preserved entity
  identities, dashboards, profiles, controls, policies, tariff history and the
  saved overnight request. Live diagnostics and appliance readiness passed;
  actual negative-window appliance execution is still to be observed. Main and
  stable v1.5.7 are unchanged.
- Implemented the approved repeat-scheduling follow-up on a separate repair
  branch, not main or a release. 322 tests pass, including malformed/overflowing
  history and command-time price revalidation regressions, a five-run synthetic
  timeline and real minimum-HA repeat/persistence/fresh-safety acceptance.
  Normal permissions and manual cooldown overrides remain intact. No live
  commands, release or HACS submission changes were made.

- Merged runtime safety, planning-boundary and initial onboarding work through
  PR #16 on 12 October at `c16b9e9`. All five post-merge checks pass, including
  285 unit tests. This supersedes the earlier local-only status below; stable
  version and production installation were not changed by that merge.

- Completed the approved planning-boundary follow-up on `fix/runtime-data-safety`:
  calendar fetching and event filtering include the full learned cycle tail,
  including startup restoration and a capture finishing during the scan.
  Candidate start horizons and learning are unchanged. 285 unit tests and real
  minimum-HA calendar-range acceptance pass locally; PR #16's latest remote
  checks, human review and any merge/release remain separate gates.

- Implemented the approved runtime repairs locally, not in a published release:
  missing power cannot finish/learn a capture; mandatory no-run source failures
  block readiness and automatic execution, including saved plans and fallbacks.
  Source recovery, multi-source editing, all-day calendar timezone, existing
  learning and manual cooldown behavior have isolated regression coverage.
  Main, versions and the live installation are unchanged.

- Prepared documentation-first onboarding on `docs/onboarding-clean-install`:
  explicit safe programme policies, separate Home Connect activation and advisory
  EV guides, a standard-card starter dashboard, compatibility and troubleshooting.
  Added executable examples and real minimum-HA fresh-install/reload/restart checks.
  Runtime code, installed HA, main and release versions are unchanged. Guided
  setup and human/physical acceptance remain separate; see
  `docs/onboarding-acceptance.md`.

- Reviewed public documentation and HACS release behaviour. Corrected stale EV
  editing/publication-gate claims, focused the README on released features and
  documented release channels, notifications and honest statistics limits.
  Removed 14 merged branches and archived one superseded prototype as a
  non-release tag, retaining `main` and both active tariff betas with their gates
  intact. See `docs/branch-cleanup-2026-10-09.md`. Documentation-only changes
  do not replace existing release tags or change installed Home Assistant code.
- Completed the static security/privacy review and merged v1.5.7 fixes: private
  diagnostic allowlisting, administrator-only maintenance, bounded atomic
  imports, planner/HTTP limits, safe command handover and removal of unused
  add-on networking. 221 unit tests, real-HA security/lifecycle checks and all
  five main CI jobs pass. Added private vulnerability reporting and policies.
  Published stable v1.5.7 and submitted HACS catalogue PR #11744; all upstream
  checks passed and maintainer review remains pending. Published separate
  v1.7.0-beta.5 with the same fixes plus administrator-only history/AI actions,
  271 unit tests and green checks. No live deployment was performed by this task.
- Installed v1.7.0-beta.4 with the stable EV editor and minimum-HA compatibility
  fix after fresh idle/no-queue/no-capture checks. One restart; all 222 entity and
  device identities and the exact dashboard configuration are unchanged.
  Learning remains 114 / 189 / 46, MixedLoad 4 / 61%, history 91 days, and all
  appliance cost statuses are ready. Live EV form/menu/defaults pass without
  saving production settings; integration logs are clean. 259 beta tests pass.
- Published stable v1.5.5's EV editor and follow-up v1.5.6 compatibility fix.
  Expanded real minimum-HA acceptance found and fixed a newer-only device-link
  API in appliances/orchestration; 209 stable unit tests and all main CI checks
  pass. At that stage the owner-led HACS application was prepared but not
  submitted; the reviewed v1.5.7 submission above supersedes that record.
- Passed the final real-wash publication gate on 9 October: MixedLoad completed
  at 13:36 BST, dishwasher learning increased 113 to 114, and MixedLoad increased
  3 to 4 runs with 61% confidence. The request cleared, completion was confirmed,
  no active captures remained and integration diagnostics were clean.
- Verified the EV options editor in isolated Home Assistant 2024.12 using synthetic
  sources: real browser form/save/error display, independent settings, clearable
  references, reload and persisted restart. Fixed deadline form serialization
  and unset-description EV labels; 204 unit tests pass. No production restart or
  dishwasher/charger command was used for this work.
- Published v1.5.4 and deployed the same scheduling/startup fixes in
  v1.7.0-beta.3 (245 tests). Live forecasts and MixedLoad selection restored;
  dishwasher / washing machine / vacuum learning totals remain 113 / 189 / 46,
  MixedLoad remains 3 runs at 51%, and all 91 tariff-history days are preserved.
  No wash was started by deployment verification. The subsequent physical wash
  passed the publication gate as recorded above; these are the earlier totals.
- Published v1.5.0 with a configurable regional Ofgem benchmark, tariff-local
  24/48-hour chart, visible benchmark and Now lines, and bottom-of-page capabilities.
- Implemented v1.6 beta source-shared tariff history and deterministic analysis,
  native entities, event refresh, explicit warm-up/incomplete-data states,
  manual re-analysis and portable history export; live rollback/upgrade tested.
- Deployed v1.7.0-beta.1 on the owner's instance; 212 combined tests passed.
  Approved official backfill imported 90 complete days / 4,320 exact-tariff prices,
  not the mismatching old cache. Read-back, disk provenance, restart and actual
  downgrade/re-upgrade passed with unchanged 113 / 189 / 46 learning totals.
- Matched the owner's Ofgem benchmark to live tariff region D (Merseyside and
  Northern Wales), not the separately named North Western England region G.
- Prepared v1.5.1 publication documentation, corrected minimum HA compatibility
  and added a single learned-hub guard. This is independent of beta promotion.
- Implemented a separate EV options editor with retained entry/entity identity,
  independent benchmark settings, clearable references and local-HH:MM deadline
  validation. Isolated options/reload/restart/rollback acceptance is recorded in
  `docs/ev-options-beta.md`; tariff beta promotion remains independent.
- Added the Lab dashboard's Automation Capabilities summary to the supported
  full and public dashboards.
- Added a configurable, daily cached regional Ofgem default-tariff benchmark as
  the first independently testable Tariff Intelligence beta slice.

- Clarified instance runtime status so active capture reports `capturing` while
  configuration health remains separately available.
- Bounded published cost-forecast attributes to stay below Home Assistant's
  Recorder state-attribute limit while retaining the full internal forecast.

- Per-instance earliest-start and latest-finish constraints.
- Selectable `cheapest_absolute`, `cheapest_earliest_finish`, and
  `cheapest_latest_finish` scheduling strategies.
- Recommended start, finish, cheapest, greenest, and potential-saving sensors.
- Profile-integrated energy and configurable fixed, water, and wear operating
  costs.
- Policy-gated automatic negative-price handling with cooldowns and run limits.
- Dishwasher automation readiness traffic lights, remote-activation preflight,
  persistence-safe opt-ins, and missed/successful start notifications.

## Scheduling And Cost Estimation

The following sections retain longer-term design ideas. Already released
strategies, cost components, helper constraints and capture-status improvements
above are not outstanding work merely because their original proposal is below.

Load Optimizer should remain device-agnostic while improving the user-facing
experience around tariff windows and run recommendations. Community Agile-window
projects show useful patterns, but Load Optimizer should not become Octopus-only
or rely only on fixed-duration appliance assumptions.

Energy suppliers and tariff integrations should be treated as provider layers.
The core optimiser should consume normalized prices, green windows, deadlines,
and local-energy context rather than embedding provider-specific behaviour.

Planned scheduling features:

- helper-driven deadline support via Home Assistant input helpers
- optional calendar integration, with TripIt recommended for travel-aware
  scheduling where users already expose TripIt to Home Assistant
- optional green-window integration, with provider-neutral carbon-intensity,
  renewable forecast, or solar/battery calendars as possible low-carbon signals
- scheduling strategies that are separate from constraints:
  `cheapest_earliest_finish`, `cheapest_latest_finish`, and `cheapest_absolute`
- future environmental strategies such as `greenest`, `balanced`, and
  `greenest_if_within_budget`
- a recommended-window active state for dashboards and automations
- a manual recalculation service for tariff, policy, or test changes
- a simple fallback estimator when only runtime and total kWh are known
- a guided Home Assistant configuration flow in a future integration phase

The preferred cost model is profile-weighted. Instead of multiplying total kWh
by an average tariff price, the optimiser should map the learned power profile
onto each candidate tariff window. This matters for long appliance cycles where
most energy is consumed during a small number of heating or charging phases.

Per-instance constraints should support common real-world rules such as:

- only run overnight
- finish before a household wake-up time
- avoid noisy spin phases late at night
- allow opportunistic operation during negative-price windows
- reserve maintenance or high-consumption cycles for special conditions

Scheduling strategies should rank only the candidates left after constraints are
applied. A deadline answers "what is allowed"; a strategy answers "which allowed
slot is preferred." For example, a dishwasher before work travel may use a
calendar-derived deadline with `cheapest_earliest_finish`, while an EV may use a
departure deadline with `cheapest_latest_finish`.

Calendar integration should be optional for basic operation but recommended for
full automation. The first implementation should prefer a helper contract such
as an enabled flag plus a must-finish-by datetime, so TripIt, Google Calendar,
Outlook, or manual Home Assistant automations can all drive the same scheduler.
Direct calendar polling can be added later as a convenience layer.

Green-window scheduling should show the cost tradeoff explicitly. A household
may want to know both "what is the cheapest possible run?" and "what would it
cost to choose the greenest acceptable run instead?" The app should therefore
publish the cheapest candidate, the greenest candidate, and the extra cost of
choosing the greener option when a green-window provider is configured.

The project may expose binary sensors later, but the core model should first
publish enough state for either binary sensors or ordinary sensors to be built
on top.

## Inferred Cycle Classification

Some appliances do not expose a selected program or operation state to Home
Assistant. Washing machines connected only through a smart plug are a good
example: the app can see power and energy, but not whether the user selected a
short spin, rinse, cotton wash, eco wash, or maintenance cycle.

An optional future classifier could infer a probable cycle class from the learned power
signature. Useful signals include:

- total runtime
- total energy
- peak power
- number and timing of heating phases
- number and timing of spin-like high-power bursts
- idle gaps or soak periods
- energy distribution across the cycle

This must be an explicit opt-in, not automatic fragmentation of existing washing
machine learning. The owner has requested that the current learning settings be
preserved. A future implementation should stay conservative. A dumb washing machine can
initially learn under `Default`, then later split learned runs into inferred
classes such as `ShortSpin`, `Wash`, `EcoWash`, `Rinse`, or `Maintenance` once
there is enough evidence. Inferred classes should be visible to the user and
remain overrideable through explicit program policies.

For the first washing-machine classifier, expect a small number of practical
classes rather than an exhaustive programme list. The initial target is likely
three broad usage patterns:

- short spin or drain-style cycles
- normal wash cycles
- longer, hotter, or maintenance-style cycles

This classification should support cost estimation as well as recommendation:
two cycles with the same total energy can have very different costs when their
high-power phases land in different tariff windows.

## Runtime Status Clarity

Instance status should distinguish between configuration health and active
capture state. Today `sensor.load_optimizer_N_cycle_state` correctly reports
`running` during a detected cycle, while `sensor.load_optimizer_N_status` can
still report `ready`.

Future versions should expose a clearer instance status such as `capturing`
while preserving separate health and configuration indicators. This will make
live monitoring easier to understand without changing the underlying cycle
state model.

## True Operating Cost

Initial optimisation will use electricity cost only.

Future versions may calculate a broader operating cost incorporating:

- water consumption
- water disposal or sewerage charges where applicable
- detergent and other consumables
- appliance wear
- battery degradation for applicable devices
- other configurable per-cycle costs

These costs should be configurable per program policy. Examples include a fixed
dishwasher tablet cost, a pence-per-litre water cost, an estimated litres-per-run
value, and a depreciation or wear allowance. Energy-only recommendations can
remain available, but the broader model should support a true operating cost and
show energy cost separately from non-energy costs.

Standing charges should normally be excluded because running a cycle does not
change them.

This broader cost model will be particularly relevant when evaluating negative
electricity prices. Consuming electricity may appear profitable while still
incurring water, consumable, and equipment costs.

Future versions should also support local energy context. For homes with solar
panels, battery storage, or both, the cheapest grid-import slot may not be the
true cheapest operating slot. The optimiser should eventually be able to factor
in available solar generation, battery state of charge, charge/discharge limits,
round-trip efficiency, export value, and whether stored energy should be
reserved for other household loads. The first version of this should be
optional, sensor-driven, and supplier-agnostic.

Negative-price automation should remain opt-in per program. When electricity is
negative, the optimiser should prefer useful, high-consumption, short-duration
programs that are explicitly marked as eligible, while respecting cooldowns,
maintenance limits, and any future additional operating-cost model.

## Completed Appliance Infrastructure Cleanup

The retired local appliance packages, templates, helper definitions, dashboards,
and Pyscript files have been removed from this repository. Future work should
continue to keep the public project focused on the installable integration.

Energy-provider helper layers are a separate integration concern. They should be
reviewed independently from the appliance cleanup so useful Octopus or tariff
logic is not removed accidentally.
