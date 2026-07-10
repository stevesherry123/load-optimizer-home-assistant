# Changelog

## Unreleased

- Remove retired local Home Assistant package, helper, template, dashboard, and
  Pyscript scaffolding from the public repository.
- Update architecture, naming, and setup documentation to describe the
  installable App as the supported runtime.

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
