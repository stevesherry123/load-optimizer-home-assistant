# Optional dashboard

The HACS package includes a standard Lovelace YAML dashboard at:

```text
/config/custom_components/load_optimizer/dashboard.yaml
```

Home Assistant does not let a custom integration register a user dashboard
without changing the user's Lovelace configuration. The integration therefore
ships and updates the dashboard file, while the user opts in by adding it to the
`lovelace` section of `configuration.yaml`:

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

The dashboard is a template, not automatic entity discovery. It uses only
standard Home Assistant cards and integration entities. The examples assume
appliance IDs 1, 2 and 3 and a Volvo-titled EV entry. Remove views/cards for loads
you do not have and replace EV entity IDs with those shown on your EV device.
Optional diagnostic entities may be disabled or unpublished in your settings.

For customisation, use your own copy outside `custom_components/` and change
the `filename` above. HACS replaces the packaged template during updates. The
integration never deletes or replaces your storage-mode dashboards.

## Automatic Scheduling Explanation

The Overview and Appliances views include an Automatic Scheduling card in the
full and standard templates respectively. It separates a candidate recommendation
from a saved start request: a ready programme is not a promise that a wash will
start. It shows the queued programme/time, last automatic request, actual start
attempt, learning confidence, outstanding safety checks and recent decisions.

`sensor.load_optimizer_1_automation_explanation` supplies the reasons from the
native scheduler, rather than reproducing the scheduling rules in dashboard
templates. An already-used overnight reservation is amber, not green. Scheduling
events are bounded to the most recent 20 and stored with the native controls,
so diagnosis does not depend on Recorder being enabled for optimizer sensors.
Existing history is not reconstructed or guessed during an upgrade.

Dates use Home Assistant's configured home timezone, including its timezone
abbreviation, even when the dashboard is opened while travelling. The card falls
back to the existing queue and attempt records on older integration versions.
It does not start, cancel or re-arm a wash. The new sensor and durable reasons
require the scheduling-diagnostics update; adding the card alone does not fix
older scheduling behaviour.

Manufacturer updates can produce short power captures. A rejected capture without
a newly learned wash or an observed Bosch running operation must not confirm a
wash or cancel its pending overnight request. A real observed wash may still
complete without entering learning, for example if its capture was interrupted.
Live verification of this distinction is a publication gate for the fix branch.

The richer example dashboards under `homeassistant/dashboards/` use
`apexcharts-card`. Their future-price axes are formatted in the tariff timezone
published by Load Optimizer, not the viewing browser's timezone. This keeps the
tariff-day view aligned when opened while travelling. It shows today's 24 hours
until next-day data arrives, then today and tomorrow across 48 hours. The Ofgem
benchmark and Now lines use the same tariff-local time basis. These richer
examples are not automatically installed by HACS.
