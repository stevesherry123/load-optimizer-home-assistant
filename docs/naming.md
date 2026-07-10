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

Those names may still exist in a user's Home Assistant instance as source
sensor names, but the App should not create or document them as managed public
state.

## Entity Categories

### Runtime State

- `load_optimizer_1_status`
- `load_optimizer_1_cycle_state`
- `load_optimizer_1_sample_count`

### Current Cycle Data

- `load_optimizer_1_power`
- `load_optimizer_1_energy`
- `load_optimizer_1_program`
- `load_optimizer_1_peak_power`

### Learned Summary Data

- `load_optimizer_1_last_program`
- `load_optimizer_1_last_runtime`
- `load_optimizer_1_last_energy`
- `load_optimizer_1_last_finish`
- `load_optimizer_1_last_profile`
- `load_optimizer_1_total_runs`
- `load_optimizer_1_learned_programs`
- `load_optimizer_1_program_model`
- `load_optimizer_1_program_policies`

### Cost And Recommendation Data

- `load_optimizer_1_cost_status`
- `load_optimizer_1_cheapest_start`
- `load_optimizer_1_cheapest_cost`
- `load_optimizer_1_cost_if_started_now`
- `load_optimizer_1_potential_saving`
- `load_optimizer_1_cost_confidence`
- `load_optimizer_1_recommended_program`

## Notes

- Keep adapter-specific source names out of the public dashboard labels.
- Use human-friendly display names in the UI, but stable `load_optimizer_*` entity IDs underneath.
