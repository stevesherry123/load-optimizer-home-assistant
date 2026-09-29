# Load Optimizer Recovery Watchdog

This optional Home Assistant package watches `sensor.load_optimizer_status` and
reloads the learned-appliance integration entry when its status has become
stale.

## Why it exists

The integration normally refreshes itself through Home Assistant's coordinator.
This package provides a conservative second layer that checks whether a healthy
status update was actually received and requests a config-entry reload if not.

It cannot reconstruct samples from a period when the add-on was unavailable.
Its purpose is to shorten future outages and make recovery visible.

## Install and enable

1. Install `load_optimizer_recovery_watchdog.yaml` as a Home Assistant package.
2. Restart Home Assistant or reload the package configuration.
3. Leave recovery disabled initially and use
   `input_button.load_optimizer_recovery_restart_now` to test a safe manual
   reload.
4. Once the manual test reports `recovered`, enable
   `input_boolean.load_optimizer_recovery_enabled`.

Defaults are deliberately conservative:

- Stale threshold: 10 minutes.
- Reload cooldown: 30 minutes.

The recovery status and message helpers record why the latest action was taken.
Recovery calls `load_optimizer.recover`; it no longer requires Supervisor or
the retired Load Optimizer add-on.
