# Load Optimizer Recovery Watchdog

This optional Home Assistant package watches `sensor.load_optimizer_status` and
restarts the Load Optimizer add-on when it is stopped or its status has become
stale.

## Why it exists

The Supervisor watchdog restarts an add-on that crashes. This package also
catches the separate failure mode where the add-on container remains present but
stops publishing a healthy status update.

It cannot reconstruct samples from a period when the add-on was unavailable.
Its purpose is to shorten future outages and make recovery visible.

## Install and enable

1. Install `load_optimizer_recovery_watchdog.yaml` as a Home Assistant package.
2. Restart Home Assistant or reload the package configuration.
3. Confirm `input_text.load_optimizer_recovery_addon_slug` is
   `f5537f93_load_optimizer`.
4. Leave recovery disabled initially and use
   `input_button.load_optimizer_recovery_restart_now` to test a safe manual
   restart.
5. Once the manual test reports `recovered`, enable
   `input_boolean.load_optimizer_recovery_enabled`.

Defaults are deliberately conservative:

- Stale threshold: 10 minutes.
- Restart cooldown: 30 minutes.

The recovery status and message helpers record why the latest action was taken.
