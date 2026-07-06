# Deployment

## Goal

Deploy `load_optimizer_1` into Home Assistant alongside the legacy dishwasher flow, validate it on real cycles, then retire the old path once the new one is trusted.

## Files To Install

From this repository, the first dishwasher rollout needs:

- `homeassistant/helpers/instances/load_optimizer_1.yaml`
- `homeassistant/templates/instances/load_optimizer_1.yaml`
- `homeassistant/packages/load_optimizer_1_package.yaml`
- `homeassistant/pyscript/core/load_optimizer_1.py`
- `homeassistant/pyscript/adapters/dishwasher_1.py`
- `homeassistant/migrations/legacy_to_load_optimizer_1/migrate_legacy_dishwasher.py`

## Suggested Home Assistant Placement

### Package Option

If you use Home Assistant packages, prefer:

- `homeassistant/packages/load_optimizer_1_package.yaml`

This bundles the helpers and template sensors into a single file.

### Helpers

Merge the contents of:

- `homeassistant/helpers/instances/load_optimizer_1.yaml`

into your helper definitions in the place where you currently manage custom helpers.

### Templates

Merge the contents of:

- `homeassistant/templates/instances/load_optimizer_1.yaml`

into your template sensor configuration.

### Pyscript

Copy these files into your Home Assistant `pyscript` layout:

- `homeassistant/pyscript/core/load_optimizer_1.py`
- `homeassistant/pyscript/adapters/dishwasher_1.py`

Keep the adapter import path intact so the core can import:

- `adapters.dishwasher_1`

### Migration Service

Copy:

- `homeassistant/migrations/legacy_to_load_optimizer_1/migrate_legacy_dishwasher.py`

into a temporary migration location inside your `pyscript` setup.

## Deployment Order

1. Add the new helper entities.
2. Add the new template sensors, or use the package file instead.
3. Add the Pyscript adapter and core files.
4. Reload helpers, templates, and Pyscript.
5. Confirm the new `load_optimizer_1_*` entities exist.
6. Run the migration service.
7. Validate the migrated data.
8. Leave the legacy dishwasher path enabled while the new path is observed on real cycles.

## Migration Run

After the files are loaded, run the migration service:

- `pyscript.migrate_legacy_dishwasher_to_load_optimizer_1`

This should copy the legacy dishwasher helper values into the new namespace.

## Parallel Validation Period

Do not remove the legacy dishwasher flow yet.

Run both systems side by side until:

- cycle start is detected reliably
- sampled profile values are written
- runtime and energy values are sensible
- delayed start does not trigger a false cycle start
- learned summaries match expectations

## Retirement Trigger

Only disable and delete the legacy dishwasher files once the new path has completed multiple real cycles successfully and its learned outputs are trusted.
