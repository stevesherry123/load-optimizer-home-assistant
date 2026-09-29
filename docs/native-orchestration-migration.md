# Native orchestration migration

The dishwasher YAML package must remain installed during the first migration
phase. The integration captures its helper values and automation state before
any native entity or controller takes ownership.

1. Install a migration-capable prerelease.
2. Call `load_optimizer.prepare_orchestration_migration`.
3. Confirm `sensor.load_optimizer_orchestration_migration` is `prepared`.
4. Keep all legacy automations enabled while native orchestration runs in shadow
   mode and compares decisions without issuing appliance commands.
5. Disable the legacy automations only after shadow verification passes.
6. Remove the YAML package only when the migration sensor reports
   `safe_to_remove_package: true`.

The integration deliberately cannot mark the package removable in the capture
phase. This prevents a partial migration from silently removing Bosch safety,
request scheduling, or cycle outcome handling.
