# Changelog

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
