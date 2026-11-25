# Load Optimizer Beta Dashboards

These optional, shareable layouts are storage-mode Home Assistant dashboards.
They are not HACS releases or integration upgrades.

| Layout | Template | Suggested dashboard URL |
| --- | --- | --- |
| **Beta V2 (recommended)** | [`load_optimizer_beta_v2.yaml`](load_optimizer_beta_v2.yaml) | `load-optimizer-beta-v2` |
| **Original Beta (V1)** | [`load_optimizer_beta.yaml`](load_optimizer_beta.yaml) | `load-optimizer-beta` |

V2 puts **Program Catalogue** first on Learning, followed by the washing machine
and robot vacuum. It omits the duplicate **Dishwasher learning** and
**Automation Capabilities** cards. V1 is retained for reference or restoration.
Both layouts keep the same Overview and Dishwasher views. Diagnostics includes
the execution record, sources, readiness and recent decisions.

Create a separate dashboard and paste your chosen template into its raw
configuration editor. Existing Home Assistant dashboards are independent saved
copies. Upgrading the integration does not overwrite them, and removing one
does not remove the integration, learning data or appliance controls.

The templates assume appliance IDs 1, 2 and 3, existing native dishwasher
controls, `apexcharts-card` and optional `card-mod`. Adapt entity references
for another installation. The optional charging link opens a separate test
bench only where one exists. Start and cancellation actions require confirmation;
review all four tabs without confirming a command or toggling automatic modes.

Regenerate both templates after editing the builder or shared chart sources:

```sh
python dev/build_dashboard_beta.py
python tests/ha_beta_dashboard_smoke.py
```
