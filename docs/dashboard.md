# Optional dashboard

The integration ships a standard Lovelace YAML dashboard at:

```text
/config/custom_components/load_optimizer/dashboard.yaml
```

Add it to the `lovelace` section of `configuration.yaml`:

```yaml
lovelace:
  mode: storage
  dashboards:
    load-optimizer:
      mode: yaml
      title: Load Optimizer
      icon: mdi:home-lightning-bolt-outline
      show_in_sidebar: true
      filename: custom_components/load_optimizer/dashboard.yaml
```

The dashboard uses only standard Home Assistant cards and integration entities.
Learned-appliance IDs remain stable. EV entity IDs are derived from the config
entry title, so edit the EV view when the configured vehicle has a different
name.

The richer example dashboards under `homeassistant/dashboards/` use
`apexcharts-card`. Their future-price axes are formatted in the tariff timezone
published by Load Optimizer, not the viewing browser's timezone. This keeps the
full available tariff horizon visible when the dashboard is opened while
travelling.
