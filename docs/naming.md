# Naming

## Rule

Use `1` as the first instance suffix everywhere.

This allows:

- a second dishwasher later
- a replacement appliance without breaking the schema
- a washing machine instance alongside a dishwasher instance
- future EV support under the same model

## Namespace Shape

Use:

- `load_optimizer_1_*`
- `load_optimizer_2_*`
- `load_optimizer_3_*`

Do not use shared public names like:

- `dishwasher_*`
- `washing_machine_*`

Those names can exist only in adapter mapping code or legacy migration files.

## Entity Categories

### Runtime state

- `load_optimizer_1_learning_active`
- `load_optimizer_1_cycle_state`
- `load_optimizer_1_cycle_start`
- `load_optimizer_1_cycle_start_energy`

### Current cycle data

- `load_optimizer_1_cycle_program`
- `load_optimizer_1_cycle_profile`
- `load_optimizer_1_cycle_sample_count`
- `load_optimizer_1_peak_power`

### Learned summary data

- `load_optimizer_1_last_program`
- `load_optimizer_1_last_runtime_minutes`
- `load_optimizer_1_last_energy_kwh`
- `load_optimizer_1_last_finish`
- `load_optimizer_1_learning_database`
- `load_optimizer_1_learning_summary`

### Prediction data

- `load_optimizer_1_expected_runtime`
- `load_optimizer_1_expected_energy`
- `load_optimizer_1_recommendation`
- `load_optimizer_1_scheduled_start`

## Migration Mapping

Legacy entity names should be migrated into the new namespace wherever the meaning still exists.

Examples:

- `input_boolean.dishwasher_learning_active` -> `input_boolean.load_optimizer_1_learning_active`
- `input_text.dishwasher_cycle_profile` -> `input_text.load_optimizer_1_cycle_profile`
- `input_text.dishwasher_last_program` -> `input_text.load_optimizer_1_last_program`
- `input_number.washing_machine_learning_active` -> `input_boolean.load_optimizer_2_learning_active` if that washing machine becomes instance 2 in the public model

## Notes

- Keep adapter-specific source names out of the public dashboard labels.
- Use human-friendly display names in the UI, but stable `load_optimizer_*` entity IDs underneath.

