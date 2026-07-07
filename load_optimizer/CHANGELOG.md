# Changelog

## Unreleased

- Document true operating cost as a deferred architectural consideration for
  water, consumables, equipment wear, and applicable battery degradation.
- Add a sanitized appliance and program-policy configuration example.

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
