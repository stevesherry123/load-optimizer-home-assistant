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

## Free And Negative-Price Runs

With native control active and automatic negative-price mode enabled, only
enabled programmes whose policy allows negative-price runs can be selected.
Prices at or below zero count, including an explicitly configured special-price
overlay. A separate promotional calendar does not itself change tariff prices
or subscribe the household to an offer.

An eligible start at the actual scan time takes precedence over a later, cheaper
slot. Within that group, programme priority and learned energy per minute retain
their existing ranking. The dashboard's negative-price programme options use the
same ordering as the controller's recommendation.

After a confirmed cycle completes, the controller can choose another permitted
programme without requiring the door to be reopened. Normal programme cooldowns
do not prohibit these opportunistic runs. Each programme's
`maximum_runs_per_window` still applies: `1` permits one run of that programme
in a continuous free/negative window, while `0` means unlimited. A positive-price
gap creates a separate window with its own allowance. The controller also keeps
its minimum 30-minute interval between automatic negative-price requests.

The learned high-power section must fit within one free/negative window. A
low-power tail may finish later and incur positive-price electricity costs;
the cost estimate includes this. Deadlines, blocked windows, complete pricing
coverage and all physical safety checks remain in force. Pending requests are
not silently replaced, and neither native control nor either automatic mode is
enabled by this scheduling change.
