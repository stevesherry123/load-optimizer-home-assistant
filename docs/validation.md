# Validation

## Pre-Check

Before running a real cycle, confirm these entities exist:

- `input_boolean.load_optimizer_1_learning_active`
- `input_text.load_optimizer_1_cycle_program`
- `input_text.load_optimizer_1_cycle_profile`
- `input_text.load_optimizer_1_learning_database`
- `input_text.load_optimizer_1_learning_summary`
- `input_number.load_optimizer_1_cycle_sample_count`
- `input_number.load_optimizer_1_cycle_start_energy`
- `input_number.load_optimizer_1_peak_power`
- `input_number.load_optimizer_1_last_runtime_minutes`
- `input_number.load_optimizer_1_last_energy_kwh`
- `input_number.load_optimizer_1_expected_runtime`
- `input_number.load_optimizer_1_expected_energy`
- `input_datetime.load_optimizer_1_cycle_start`
- `input_datetime.load_optimizer_1_last_finish`
- `sensor.load_optimizer_1_selected_program`
- `sensor.load_optimizer_1_cycle_state`
- `sensor.load_optimizer_1_recommendation`
- `sensor.load_optimizer_1_scheduled_start`

## Migration Check

After running the migration service, confirm:

- last program was copied
- learning database was copied
- learning summary was copied
- expected runtime and expected energy were copied
- last finish, runtime, and energy values look sensible

## Runtime Check

During a real dishwasher cycle, confirm:

1. `input_boolean.load_optimizer_1_learning_active` turns `on`.
2. `input_text.load_optimizer_1_cycle_program` shows the expected program.
3. `input_text.load_optimizer_1_cycle_profile` begins filling with semicolon-separated power samples.
4. `input_number.load_optimizer_1_cycle_sample_count` increases.
5. `input_number.load_optimizer_1_peak_power` rises to a sensible dishwasher peak.
6. `input_text.load_optimizer_1_cycle_state` stays at `RUNNING` during the cycle.

## Finish Check

At cycle completion, confirm:

1. `input_boolean.load_optimizer_1_learning_active` turns `off`.
2. `input_datetime.load_optimizer_1_last_finish` updates.
3. `input_number.load_optimizer_1_last_runtime_minutes` updates.
4. `input_number.load_optimizer_1_last_energy_kwh` updates.
5. `input_text.load_optimizer_1_learning_database` reflects the completed run.
6. `input_text.load_optimizer_1_learning_summary` updates.
7. `input_number.load_optimizer_1_expected_runtime` updates for the learned program.
8. `input_number.load_optimizer_1_expected_energy` updates for the learned program.

## Delayed Start Check

When the Bosch dishwasher is in delayed start:

- `input_text.load_optimizer_1_cycle_state` should show `DELAYED_START`
- the learning flag should remain `off`
- no profile samples should be appended

## Comparison Check

For the first few runs, compare the new entities against the legacy dishwasher entities:

- start time
- program
- last runtime
- last energy
- learning summary
- learning database

If the new values are materially worse, keep the legacy path active and fix the new path before retirement.

