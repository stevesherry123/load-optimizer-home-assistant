# Changelog

## Unreleased

- Document the provider-layer architecture so tariff, green-window, solar,
  battery, and calendar inputs remain optional context rather than core
  dependencies.

## 0.8.30

- Add execution-status publishing for optional Home Assistant start-attempt
  helpers.
- Extend the Dishwasher 1 automation package with durable start-attempt
  status, result, program, timestamp, and failure-reason helpers.
- Preserve Bosch start diagnostics separately from the scheduler request so
  failed starts can be reviewed after the request helpers are cleared.
- Re-check live Bosch/app state after each start step instead of relying on a
  stale automation-start snapshot.

## 0.8.29

- Add configurable per-program non-energy operating costs for fixed consumables,
  water, and wear-and-tear.
- Publish energy, non-energy, and total operating-cost breakdowns on cost and
  scheduling recommendation entities.
- Keep `estimated_overhead_cost_pence` as a backwards-compatible alias for the
  new `fixed_cost_pence` policy field.

## 0.8.28

- Reduce Home Assistant Recorder churn by skipping unchanged entity publishes.
- Save private app state only when learned or in-progress cycle data changes.
- Publish slimmer learned-program summaries without large profile/history arrays.
- Add `publish_diagnostics`, `publish_profile_data`, and
  `publish_cost_forecast` controls for storage-constrained installs.
- Document optional Recorder exclusions for Raspberry Pi and SD-card
  deployments.

## 0.8.27

- Publish compact per-instance profile data for dashboard power-profile charts.

## 0.8.26

- Detect Bosch dishwasher learned programs that are not available in the Home
  Assistant program selector before attempting a start.
- Report the unavailable program key and selectable Bosch options in the
  scheduler message helper.

## 0.8.25

- Write dishwasher execution breadcrumbs to the scheduler message helper after
  each Bosch start stage.
- Keep a visible success or failure summary in the scheduler helper after a
  manual start request completes.

## 0.8.24

- Make dishwasher failed-start diagnostics concise enough to appear in the
  announcement and scheduler helper.
- Try the standard Home Connect `start_program` service after the Home Connect
  Alt fallback if the Bosch button path still does not report a running cycle.

## 0.8.23

- Treat `QuickD` as its own Bosch dishwasher program key instead of mapping it
  to `Quick45`.

## 0.8.22

- Harden the dishwasher start automation by calling the Bosch power, program,
  and start entities directly.
- Preserve the dishwasher scheduler diagnostic message after a failed start
  attempt.
- Add Bosch selected-program and power-state details to failed-start
  diagnostics.

## 0.8.21

- Fix the runtime status entity reporting the old `0.8.18` app version after
  newer add-on releases were installed.
- Publish `sensor.load_optimizer_N_recommended_finish` for dashboard cards that
  need a first-class recommended finish timestamp entity.

## 0.8.20

- Harden the example Bosch dishwasher execution automation.
- Check Bosch connectivity, door, remote-control, and remote-start readiness
  before attempting a start.
- Power on the appliance, select the Bosch program entity, and press the Bosch
  start button before falling back to the direct Home Connect start service.
- Keep the scheduler diagnostic message visible after failed start attempts.

## 0.8.19

- Enforce `minimum_hours_between_runs` during scheduling and cost forecasting.
- Reject candidate start times that fall inside a program cooldown window so the
  optimiser can fall through to the next eligible cycle type.
- Publish cooldown diagnostics, including `cooldown_until`,
  `rejected_cooldowns`, and `reason: cooldown_active`.

## 0.8.18

- Add helper-driven travel/deadline scheduling constraints through
  `schedule_earliest_start_entity` and `schedule_latest_finish_entity`.
- Reject candidate starts that would finish after an active latest-finish
  deadline, while ignoring expired helper values.
- Add an optional Home Assistant TripIt-style deadline package example.
- Add `minimum_hours_between_runs` and `negative_price_priority` program-policy
  fields for the next negative-price automation phase.
- Treat `maximum_runs_per_window: 0` as unlimited for future negative-price
  planning.

## 0.8.17

- Add `sensor.load_optimizer_N_discovered_programs` to flag learned programs
  that do not yet have explicit policies.
- Add `sensor.load_optimizer_N_negative_price_recommendation` for automatic
  negative-price opportunity planning.
- Rank negative-price candidates by useful energy intensity so high-consumption,
  short-duration programs are preferred when users explicitly allow them.

## 0.8.16

- Add `sensor.load_optimizer_N_program_catalogue` to show learned and
  configured-but-unlearned programs together.
- Keep configured zero-run programs visible with policy, classification, and
  negative-price eligibility metadata.
- Support gradual real-world cycle discovery when appliance integrations do not
  expose a complete available-program list.

## 0.8.15

- Publish front-end friendly recommendation entities for `now`, `soon`, and
  `overnight` run intents.
- Include program, start, finish, cost, saving, confidence, and readiness
  attributes so Alexa, dashboards, and automations can stay simple.
- Keep the scheduling intelligence inside Load Optimizer instead of embedding
  tariff logic in voice or dashboard automations.

## 0.8.14

- Add `sensor.load_optimizer_restart_safety` to show whether restarting or
  updating the app is currently safe.
- Publish `restart_blocked` on the main status entity whenever any appliance
  cycle capture is active.
- Keep the existing interrupted-cycle protection so accidental restarts still
  discard incomplete learning data.

## 0.8.13

- Preserve usable representative power profiles when repairing suspicious
  learned cycles.
- Store compact power profiles with recent cycles so repaired learning models
  remain cost-forecastable.
- Rebuild a missing representative profile from the latest completed cycle when
  raw power samples are still available.

## 0.8.12

- Remove hardcoded `instance_1_*`, `instance_2_*`, and `instance_ids` add-on
  options from the public schema.
- Treat `instances_yaml` as the only appliance configuration source.
- Publish forecast diagnostics so missing forecast programs explain whether they
  were excluded by policy, profile quality, or tariff coverage.

## 0.8.11

- Publish forecast chart state using pence instead of forecast point count so
  ApexCharts labels generated cost values correctly.
- Keep forecast row count as the `forecast_points` attribute.
- Round estimated scheduled cost sensor states to 2 decimal places.
- Mark cheapest start sensors as timestamps for cleaner Home Assistant display.

## 0.8.10

- Add separate `cost_forecast_interval`, defaulting to 30 minutes, so charts use
  clean half-hour start times without reducing optimiser precision.

## 0.8.9

- Publish a per-instance cost forecast entity for charting estimated cycle cost
  by candidate start time and learned program.
- Add configurable `cost_forecast_hours`, defaulting to 12 hours.

## 0.8.8

- Round published pence-based cost and saving sensor states to 2 decimal
  places for cleaner dashboard cards.

## 0.8.7

- Publish separate best overnight and daytime cost comparison entities.
- Publish separate overnight and daytime savings versus starting now.
- Keep the selected recommendation logic unchanged while exposing clearer
  dashboard comparison data.

## 0.8.6

- Add schedule window preferences for `overnight_only`, `daytime_only`,
  `prefer_overnight`, and `prefer_daytime`.
- Default the overnight window to 20:00-08:00 in the configured tariff timezone.
- Publish selected window preference and whether the recommended start is
  overnight/daytime on cost and schedule entities.

## 0.8.5

- Add per-instance scheduling strategies:
  `cheapest_absolute`, `cheapest_earliest_finish`, and
  `cheapest_latest_finish`.
- Add a near-equivalent cost tolerance so earliest/latest finish strategies can
  choose between slots that cost effectively the same.
- Publish the selected strategy, cost tolerance, and recommended finish time on
  scheduling and cost entities.

## 0.8.4

- Add advisory scheduling entities for recommended start time, estimated
  scheduled cost, schedule status, and a read-only good-to-start signal.
- Add conservative schedule gating based on confidence and start-time tolerance.
- Keep scheduling read-only; this release does not trigger or start appliances.

## 0.8.3

- Add learning quality gates so suspiciously short, low-sample, or near-zero
  energy captures are discarded instead of being loaded into program models.
- Repair existing recent-cycle learning on startup by removing cycles that fail
  the same quality gates, reducing affected run counts, and clearing
  representative profiles that may already have absorbed bad data.
- Publish quality-excluded cycles through
  `sensor.load_optimizer_N_last_discarded_cycle`.

## 0.8.2

- Replace the unsupported repeatable add-on schema with a persisted
  `instances_yaml` option for scalable appliance configuration.
- Keep legacy `instance_ids` and `instance_N_*` fields active for existing
  installs while allowing unlimited instances through the YAML/JSON field.

## 0.8.1

- Exclude active cycles from learning when the app starts and detects that the
  capture was already in progress.
- Publish the excluded cycle as `sensor.load_optimizer_N_last_discarded_cycle`
  so interrupted runs remain visible without poisoning learned profiles.

## 0.8.0

- Add a repeatable `instances` add-on configuration list so the app can expand
  beyond two appliances without adding new static `instance_N_*` fields.
- Keep the older `instance_ids` and `instance_N_*` fields as backward-compatible
  configuration for existing installs while the migration path is proven.

## 0.7.10

- Remove retired local Home Assistant package, helper, template, dashboard, and
  Pyscript scaffolding from the public repository.
- Update architecture, naming, and setup documentation to describe the
  installable App as the supported runtime.
- Expose learned-program audit fields including first seen, last seen, profile
  count, and recent cycle summaries to make run-count issues diagnosable.

## 0.7.9

- Allow combined tariff sources to continue when one configured source is
  readable but currently has no rates, such as an empty next-day event before
  future Agile rates have been published.
- Publish per-source tariff parse errors without failing the whole cost
  estimator when at least one source has usable rates.

## 0.7.8

- Publish safe tariff diagnostics on cost status sensors when configured tariff
  entities are readable but do not expose a supported rate list.

## 0.7.7

- Add a Home Assistant template fallback for tariff entities whose rate lists
  are available through `state_attr()` but not returned in the normal state API
  payload.

## 0.7.6

- Add `tariff_entities` for combining multiple tariff sources, such as
  BottlecapDave Octopus Energy current-day and next-day rate events.
- Read nested tariff rate payloads from Home Assistant event entities.
- Keep `tariff_entity` as a backwards-compatible single-source option.
- Mark custom tariff feeds as compatibility sources rather than recommended
  public prerequisites.
- Document true operating cost as a deferred architectural consideration for
  water, consumables, equipment wear, and applicable battery degradation.
- Add a sanitized appliance and program-policy configuration example.

## 0.7.4

- Calculate completed-cycle energy from the captured power profile instead of
  relying primarily on daily energy counter deltas.
- Keep the energy sensor delta as diagnostic metadata when available, but avoid
  daily-counter reset problems for cycles that span midnight or follow another
  same-day cycle.
- Add regression coverage for daily energy counters resetting during a cycle.

## 0.7.3

- Expose reset request feedback on `sensor.load_optimizer_status`, including
  whether the configured reset request is pending, consumed, invalid, or partly
  invalid.
- Publish requested, processed, pending, and invalid reset IDs so users can see
  that a lingering one-shot reset value has already been handled.

## 0.7.2

- Make `reset_instance_ids` one-shot while the same value remains configured, so
  an accidental lingering reset value does not repeatedly clear new learning
  after every restart.
- Re-arm reset processing when `reset_instance_ids` is cleared.

## 0.7.1

- Add a manual `reset_instance_ids` safety valve for clearing selected
  appliance instance data without touching other instances.
- Warn through a Home Assistant persistent notification when the app starts
  while one or more instances are already mid-cycle.
- Expose active capture instances on `sensor.load_optimizer_status` to make
  restart/update interruptions visible.

## 0.7.0

- Add multi-instance appliance monitoring for the Home Assistant app.
- Keep existing installs on instance `1` by default while allowing
  comma-separated `instance_ids`, such as `1,2`.
- Publish each configured appliance under its own numbered sensor namespace,
  for example `sensor.load_optimizer_1_*` and `sensor.load_optimizer_2_*`.
- Add instance `2` add-on configuration fields for bringing a washing machine
  into the same learning and tariff-cost pipeline.

## 0.6.1

- Publish a per-tariff-window cost breakdown for profile-based estimates.
- Expose how much learned cycle energy falls into each half-hour price period.
- Preserve profile-weighted costing for cycles where high-power phases occur in
  cheaper or negative-price windows and low-power phases continue later.

## 0.6.0

- Add a read-only tariff cost-estimation engine.
- Accept optional OIE `ai_feed` and common structured Home Assistant rate data.
- Keep the tariff source configurable with no dependency on OIE or Octopus.
- Normalize prices to pence per kWh and timestamps to UTC.
- Scale representative power profiles to learned measured energy.
- Search policy-eligible five-minute start candidates and support negative prices.
- Reject incomplete tariff coverage instead of publishing a partial estimate.
- Publish cost status, cheapest start, expected cost, saving, confidence, and
  recommended program entities.

## 0.5.1

- Require only the program name and classification in each policy entry.
- Apply safe defaults when optional policy fields are omitted.
- Expose optional policy defaults on the program-policies sensor.
- Prevent incomplete but valid policy entries from disappearing on save.

## 0.5.0

- Add configurable per-program policy classifications.
- Keep user preferences separate from learned program measurements.
- Support preferred, alternative, maintenance, opportunistic, disabled, and
  unclassified programs.
- Add limits and explicit eligibility flags for normal and negative-price use.
- Publish resolved policies through `sensor.load_optimizer_1_program_policies`.

## 0.4.0

- Learn separate running statistics for each appliance program.
- Calculate expected runtime, energy, peak power, variation, and confidence.
- Build a compact representative 20-point power profile for each program.
- Publish learned models through `sensor.load_optimizer_1_learned_programs` and
  `sensor.load_optimizer_1_program_model`.
- Seed learning from the most recent compatible cycle after upgrade.

## 0.3.0

- Capture timestamped power and energy samples throughout each cycle.
- Persist the completed power profile with the learned cycle record.
- Publish the last profile through `sensor.load_optimizer_1_last_profile`.
- Preserve genuine low-power pauses while excluding the finish-confirmation tail.

## 0.2.1

- Exclude the finish-confirmation delay from learned runtime and finish time.
- Normalize Home Connect program identifiers into readable names.
- Retain the completed cycle's sample count.
- Cancel a pending finish when appliance power resumes.

## 0.2.0

- Add configurable monitoring for appliance instance 1.
- Publish the `sensor.load_optimizer_1_*` entity set automatically.
- Detect cycle starts and finishes from configurable power thresholds.
- Store run count, runtime, energy, peak power, program, and finish time.
- Remove private device identifiers from the public adapter examples.

## 0.1.0

- Add the initial Home Assistant App package.
- Add Supervisor-authenticated status publishing.
- Add persistent private data storage.
- Add an internal health endpoint for the Home Assistant watchdog.
