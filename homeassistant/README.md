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
  visible after the scheduler request has been cleared.
- `packages/load_optimizer_travel_deadline_example.yaml` adds an editable
  Dishwasher 1 must-finish-by helper and a TripIt-style calendar automation
  example that seeds the helper to 90 minutes before travel.

## Dashboards

- `dashboards/load_optimizer_dishwasher_controls.yaml` adds raw dashboard cards
  for the Dishwasher 1 request helpers and buttons.
