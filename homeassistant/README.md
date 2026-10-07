# Home Assistant examples

This folder contains optional Home Assistant YAML that can be copied into a
Home Assistant instance alongside the Load Optimizer integration.

These files are not required for the learning engine to run. They provide
example dashboards and a travel-deadline automation for users who want Home
Assistant to provide additional scheduling context.

## Packages

- `packages/load_optimizer_travel_deadline_example.yaml` adds an editable
  Dishwasher 1 must-finish-by helper and a TripIt-style calendar automation
  example that seeds the helper to 90 minutes before travel.

## Dashboards

- `dashboards/full/load_optimizer_dashboard.yaml` is the maintained richer
  dashboard for installations with `apexcharts-card`.
- `dashboards/full/dishwasher_learning_insights.yaml` provides detailed learned
  cycle and program-model visibility.
