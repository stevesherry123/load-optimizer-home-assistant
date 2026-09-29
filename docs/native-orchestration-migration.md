# Native orchestration migration

The dishwasher YAML package must remain installed during the first migration
phase. The integration captures its helper values and automation state before
any native entity or controller takes ownership.

1. Install a migration-capable prerelease.
2. Call `load_optimizer.prepare_orchestration_migration`.
3. Confirm `sensor.load_optimizer_orchestration_migration` is `prepared`.
4. Keep all legacy automations enabled while native orchestration reports
   `shadow` and compares decisions without issuing appliance commands.
5. Call `load_optimizer.activate_native_orchestration` after shadow verification.
   The service disables the package automations and persists native ownership.
6. Use `load_optimizer.deactivate_native_orchestration` to roll back before the
   package is retired.
7. Retire the YAML package only when the migration sensor reports
   `safe_to_remove_package: true`.

Fresh installations configure Bosch entity references through the integration's
Configure dialog and do not need the YAML package. Migrated installations seed
the same private configuration from the captured helper values.

The integration deliberately cannot mark the package removable in the capture
phase. This prevents a partial migration from silently removing Bosch safety,
request scheduling, or cycle outcome handling.
