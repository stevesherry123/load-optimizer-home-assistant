# Home Assistant examples

This folder contains optional Home Assistant YAML that can be copied into a
Home Assistant instance alongside the Load Optimizer App.

These files are not required for the learning engine to run. They provide
example dashboards, helpers, and automations for users who want Home Assistant
to act on Load Optimizer recommendations.

## Packages

- `packages/load_optimizer_dishwasher_automation.yaml` adds Dishwasher 1 request
  helpers, request buttons, cancellation, announcements, Bosch start
  automation, and execution-status helpers that keep the last start attempt
  visible after the scheduler request has been cleared. It also includes an
  explicitly opt-in normal automatic mode. This mode requires a new door-open
  event after the previous cycle, restart safety to be clear, and a ready
  immediate recommendation before it requests an unattended start.
  The package also creates a manual free/special-price window: set its start,
  end, price (normally `0 p/kWh`) and optional label, then enable the window.
  The existing opt-in `Auto Free / Negative Price` switch controls whether a
  qualifying recommendation may create an unattended dishwasher request.
- `packages/load_optimizer_travel_deadline_example.yaml` adds an editable
  Dishwasher 1 must-finish-by helper and a TripIt-style calendar automation
  example that seeds the helper to 90 minutes before travel.

## Dashboards

- `dashboards/load_optimizer_dishwasher_controls.yaml` adds raw dashboard cards
  for the Dishwasher 1 request helpers and buttons.
- `dashboards/experimental/load_optimizer_dashboard_v2.yaml` is a separate,
  installable design-lab dashboard. It leaves the production dashboard intact
  and exposes the full control, recommendation, learning, automation, and
  diagnostic data set for side-by-side evaluation. See the README beside that
  file for installation and removal instructions.
