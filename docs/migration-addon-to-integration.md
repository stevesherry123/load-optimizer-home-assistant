# Migrating From The Add-on To The HACS Integration

This migration keeps the existing learned-appliance behaviour while moving the
runtime into the HACS custom integration.

## What Migrates

The integration compatibility runtime publishes the same legacy state entities,
including:

- `sensor.load_optimizer_status`
- `sensor.load_optimizer_diagnostics`
- `sensor.load_optimizer_restart_safety`
- `sensor.load_optimizer_N_status`
- `sensor.load_optimizer_N_cycle_state`
- `sensor.load_optimizer_N_program_model`
- `sensor.load_optimizer_N_cost_status`
- `sensor.load_optimizer_N_now_recommendation`
- `sensor.load_optimizer_N_soon_recommendation`
- `sensor.load_optimizer_N_overnight_recommendation`
- `sensor.load_optimizer_N_negative_price_recommendation`
- `sensor.load_optimizer_N_good_to_start`

The existing Home Assistant packages and dashboards can therefore keep using
the same entity IDs while the add-on is mothballed.

## Migration Steps

Before creating the integration entry, preserve/export the old database and stop
the add-on, including its start-on-boot setting. Do not run both engines against
the same appliance. The stopped add-on and its private data remain available
for export or rollback; no uninstall is performed by the integration.

1. Install the HACS integration release.
2. Restart Home Assistant.
3. Go to Settings > Devices & services > Add integration > Load Optimizer.
4. Choose load type `learned_appliance`.
5. Paste the existing add-on `instances_yaml`.
6. Copy across the existing add-on tariff and scheduling options.
7. Save the integration entry and confirm `sensor.load_optimizer_status`
   appears.
8. Export the add-on database from `/data/load_optimizer.json`.
9. In Developer Tools > Services, call:

```yaml
service: load_optimizer.import_legacy_state
data:
  legacy_state_json: |
    {
      "schema_version": 1,
      "instances": {}
    }
```

Replace the example object with the full contents of the old add-on database.

10. Confirm `sensor.load_optimizer_migration_status` reports `imported`.
11. Confirm the expected `sensor.load_optimizer_N_*` entities have the learned
    program data and recommendations.
12. Stop the old add-on.
13. Disable "Start on boot" for the old add-on.
14. Reload the integration entry and confirm the learned run and program counts
    are unchanged, proving the imported database is persisted.
15. Take a full post-migration Home Assistant backup.
16. Uninstall the stopped add-on. Keep its add-on-only backup until the
    integration has captured at least one new complete cycle.

You can then call:

```yaml
service: load_optimizer.mothball_legacy_addon
```

This publishes a reminder sensor and notification confirming the old add-on can
be uninstalled after validation and backup.

## Notes

The add-on's private `/data` directory is not reliably readable from a HACS
custom integration, so migration is explicit rather than automatic. This avoids
guessing paths that differ between Home Assistant installations and add-on
backup layouts.

Calendar-based green or blocked windows are prefetched through Home Assistant's
calendar service before each compatibility scan. State-based window entities are
read directly from Home Assistant state, as they were in the add-on.
