# Changelog

## Unreleased

- No unreleased changes.

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
