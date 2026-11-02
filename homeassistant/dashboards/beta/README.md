# Dashboard Layout Trial

This optional dashboard trial lives on `beta/dashboard-layout`; it is not a HACS
prerelease or an integration upgrade. It uses existing integration entities.
Create a separate storage-mode dashboard named **Load Optimizer Beta** at
`load-optimizer-beta` and paste `load_optimizer_beta.yaml` into its raw editor.
Do not replace an existing dashboard or change the default dashboard.

The Overview combines the tariff-day chart, current price/Ofgem tiles, actual
queue and latest learned wash. Dishwasher separates safety/readiness, candidate
recommendations and explicit manual controls. Learning contains programme tables;
Diagnostics uses the native execution record and keeps Automation Capabilities
at the bottom. The charging link opens the existing separate test bench.

Assumptions: appliance IDs 1, 2 and 3, existing native dishwasher controls,
`apexcharts-card` and optional `card-mod`. Adapt entity IDs before installing on
another system. The charts use published source data; the dashboard does not
change tariff prices or scheduler decisions. It does not fix runtime bugs in an
older installed integration. Missing sources are not displayed as a queued wash.

Start and cancellation buttons require confirmation. Reviewing the dashboard
must not involve confirming either command or toggling automatic modes. Reload
and inspect all four tabs on desktop/mobile without operating physical loads.

Regenerate after editing the builder or shared charts:

```sh
python dev/build_dashboard_beta.py
python tests/ha_beta_dashboard_smoke.py
```

The checked-in YAML must match the builder. Dashboard copies installed in Home
Assistant are independent: switching branches or upgrading HACS does not update
them. Removing the trial dashboard does not remove entities, learning or controls.
