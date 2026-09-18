# Load Optimizer dashboard v2 design lab

This dashboard is deliberately separate from the existing production
dashboard. It can be installed alongside the current dashboard and removed
without changing any Load Optimizer entities, helpers, automations, or views.

## Requirements

- Load Optimizer app 0.8.90 or later.
- Dishwasher automation package 0.8.89 or later.
- The existing ApexCharts Card frontend resource used by the production
  dashboard.
- The optional travel-deadline package for the `must_finish_by` controls. If it
  is not installed, only those deadline rows will show as unavailable.

## Install as a second YAML dashboard

1. Upload `load_optimizer_dashboard_v2.yaml` to
   `/config/dashboards/load_optimizer_dashboard_v2.yaml`.
2. Add this entry beneath `lovelace: dashboards:` in `configuration.yaml`:

   ```yaml
   lovelace:
     dashboards:
       load-optimizer-lab:
         mode: yaml
         title: Load Optimizer Lab
         icon: mdi:flask-outline
         show_in_sidebar: true
         require_admin: true
         filename: dashboards/load_optimizer_dashboard_v2.yaml
   ```

3. Check the Home Assistant configuration and restart Home Assistant.

The URL path will be `/load-optimizer-lab/tonight`. The dashboard has six
views: Tonight, Plans & Price, Learning, Automation, System, and Other
Appliances.

## Removal

Remove the `load-optimizer-lab` dashboard entry from `configuration.yaml`,
restart Home Assistant, and then delete the uploaded dashboard file. No app or
automation-package state is stored in the dashboard.
