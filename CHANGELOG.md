# Changelog

## Unreleased

- Document true operating cost as a deferred architectural consideration for
  water, consumables, equipment wear, and applicable battery degradation.

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
