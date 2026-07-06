# Migration

## Purpose

The project should migrate data from the current dishwasher and washing machine systems into a clean public schema, then retire the legacy entities and code.

## Migration Steps

1. Inventory current Home Assistant helpers, template sensors, scripts, and automations.
2. Map each legacy entity to the new `load_optimizer_1_*` or `load_optimizer_2_*` namespace.
3. Copy across current state values.
4. Preserve historical learned summaries where the meaning is equivalent.
5. Validate dashboard and runtime behavior against the new entities.
6. Disable legacy automations and scripts.
7. Delete legacy helpers after the new system is stable.

## Data To Preserve

- learning status
- cycle start time
- start energy
- live cycle profile
- current sample count
- peak power
- last program
- last runtime
- last energy
- last finish
- learning database
- human-readable summaries

## Data To Review Carefully

- mixed or duplicate profile formats
- helper strings that contain old prototype metadata
- any entity values that were already known to be stale or dummy values

## Legacy Sources

The current source material includes:

- dishwasher learning helpers and scripts
- washing machine learning helpers and scripts
- dashboard cards for learning status, last learned cycle, current prediction, and profile capture

## Retirement Rule

Once the new schema is verified and the data has been migrated, legacy entities should be deleted rather than left behind as permanent compatibility clutter.

