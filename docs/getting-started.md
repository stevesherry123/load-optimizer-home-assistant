# Getting Started

## Before Installation

Use Home Assistant 2024.12 or later and a stable GitHub release. Install your
appliance/vehicle and tariff integrations first. This integration consumes their
entities; it does not replace your supplier or car connection.

Add this repository to HACS as an **Integration**, download the latest stable
release, restart Home Assistant, then choose Settings > Devices & services >
Add integration > Load Optimizer. Pre-releases are opt-in development builds.

## New Learned-Appliance Installation

Create one learned-appliance hub. Add all appliances to its Instances YAML
list, with a distinct ID for each. A minimal example is:

```yaml
- id: "1"
  name: Washing Machine
  power_sensor: sensor.washing_machine_power
  energy_sensor: sensor.washing_machine_energy
```

Replace the example references with your existing power sensor in watts and
total energy sensor in kWh. A program sensor is optional: appliances without
one initially learn under `Default`. Do not split a known program into inferred
classes merely to increase model counts.

In tariff settings, either select one entity containing all future prices or
provide the current-day and next-day event entities as a comma-separated list
under Additional tariff entities. For BottlecapDave Octopus `value_inc_vat`
rates, select `gbp_per_kwh`; if your source is in pence select `p_per_kwh`.
Use `Europe/London` for UK tariffs. Do not apply both unit conversions.

Choose the Ofgem electricity region matching the tariff's distribution region
and your payment method. For example, an Agile code ending `-D` uses Merseyside
and Northern Wales; `-G` uses North Western England. This only configures the
comparison benchmark and does not alter your supplier's rates.

Leave optional dishwasher-control settings empty for an ordinary smart-plug
washing machine. Automatic starting requires explicitly configured compatible
controls and opt-ins. Do not use a mains power switch as a substitute for an
appliance's supported remote-start command.

After setup, check runtime/configuration health. Recommendations may wait for a
complete learned cycle and valid future rates. Confirm a finished cycle updates
the relevant total-runs and learned-programs sensors. Add more appliances in
Configure > Appliances and tariff, not through Add hub.

## Existing Add-on Installation

Follow the [migration guide](migration-addon-to-integration.md). An empty
installation needs no database import. Importing a legacy learning database
replaces the integration's learning state, so do not use the import action on an
established installation without preserving its current state first.

## EV Planning

Create an EV entry with battery percentage, usable capacity in kWh, charge
power in kW, target percentage, efficiency and a tariff entity containing the
future rate horizon. Use real capacity, not a percentage or estimated range.
Select a connection sensor when available. The planner publishes charge-now
and ready-to-charge signals; it does not operate a charger or power plug.

Keep any charger-control automation opt-in and subject to the charger's own
safety checks. From stable v1.5.5, use the EV entry's Configure cog to change
source references, charging assumptions, deadline and benchmark settings. The
editor preserves the entry and registered entity identities; do not delete and
recreate the entry merely to edit its settings.

## Dashboard And Troubleshooting

The [dashboard guide](dashboard.md) explains the optional packaged template and
the richer ApexCharts examples. Neither is automatically added to your sidebar.

If costing is waiting, check the tariff entity attributes, price unit, future
coverage and the power/energy sensors. Use the runtime and per-appliance health
states and downloadable diagnostics before enabling automatic control. Attach
only redacted diagnostics to an issue; never include tokens or private backups.
