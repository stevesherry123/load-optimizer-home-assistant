# Getting Started

Start with one appliance, learn one complete cycle, then check its running-cost
recommendation. Automatic starting is a separate, optional step.

## Before Installation

- Use Home Assistant 2024.12 or later, HACS, and a stable GitHub release.
- Install your tariff and appliance integrations first. Load Optimizer consumes
  their entities; it does not connect directly to your supplier or appliance.
- Identify a numeric power sensor in **W** and preferably a cumulative energy
  sensor in **kWh**. A switch alone is not a power sensor.
- Check the [compatibility guide](compatibility.md) before planning device control.

In HACS, add `https://github.com/stevesherry123/load-optimizer-home-assistant` as
a custom repository of type **Integration**, then download Load Optimizer.
Restart Home Assistant and choose **Settings > Devices & services > Add
integration > Load Optimizer**. Downloading and configuring are separate steps.
Choose a stable release; prereleases are for opted-in testers.

## One Appliance: Learning And Recommendations

1. Choose load type `learned_appliance`. Create just one learned-appliance hub;
   later appliances belong in its list, not in additional hubs.
2. Paste the following **whole list** into **Instances YAML**. Replace the two
   sensor IDs with your own. Do not paste `instances_yaml: |` around this list.

```yaml
- id: "1"
  name: Washing Machine
  power_sensor: sensor.washing_machine_power
  energy_sensor: sensor.washing_machine_energy
  program_policies:
    - program: Default
      classification: preferred
      enabled: true
      allow_normal_recommendation: true
      allow_negative_price_run: false
```

The same tested example is available as
[`examples/learned-appliance.yaml`](examples/learned-appliance.yaml).

Without a programme sensor, completed cycles learn under `Default`. The explicit
policy above permits **recommendations**, not remote starting. Without an
eligible policy the appliance can learn successfully but costing reports
`no_eligible_programs`; more cycles alone will not resolve that state.

If your appliance reports its actual programme, add `program_sensor` and create a
policy for each exact name shown in the integration's Programme Catalogue, such
as `Eco50`. Do not keep only the `Default` policy when learning named programmes.
Different programmes should have separate learned profiles, not invented names
for otherwise identical runs.

## Tariff And Benchmark Fields

| Field | What to enter |
| --- | --- |
| Tariff entity | An entity whose attributes contain future prices, not just the current price. Leave blank when using the additional-entities list instead. |
| Additional tariff entities | For BottlecapDave Octopus, your current-day and next-day **rates event entities**, separated by a comma. Do not copy another household's meter IDs. |
| Tariff price unit | `gbp_per_kwh` for Octopus `value_inc_vat` values such as `0.25`; `p_per_kwh` for values such as `25`. Both represent 25 p/kWh. |
| Tariff timezone | `Europe/London` for UK tariffs, regardless of where you view the dashboard. |
| Ofgem electricity region | Match the tariff's electricity distribution region. Agile suffix `-D` uses Merseyside and Northern Wales; `-G` uses North Western England. |
| Price-cap payment method | Your payment method, such as direct debit. The benchmark is a comparison, not a ceiling on Agile prices. |
| Green / blocked window entities | Optional calendars. Leave blank unless you have the corresponding entities and want these constraints. |

Leave refresh timing, cost-search and publishing settings at their defaults
initially. Change them later through the Configure cog. Today's rates can be
usable before tomorrow's arrive; a candidate needs complete prices through its
finish time.

The current appliance form accepts YAML without a full pre-save validation
screen. Check indentation, distinct positive numeric IDs and exact entity IDs.
Saving a form is not proof that every source is usable. For kW or Wh sources,
supply correctly converted W/kWh sensors rather than relabeling their units.
See [troubleshooting](troubleshooting.md).

## Confirm Your First Result

For appliance ID `1`, inspect these entities in **Developer tools > States** or
on the [small starter dashboard](dashboard.md#start-with-one-appliance):

| Milestone | Expected result |
| --- | --- |
| Sources connected | `sensor.load_optimizer_1_power` and `_energy` reflect your source sensors. |
| Appliance used normally | `_cycle_state` becomes `running`, then returns to `idle`. |
| Complete cycle learned | `_total_runs` increases by one and `_learned_programs` includes `Default` or the actual programme. |
| Costing available | `_cost_status` becomes `ready`; `_recommended_program`, `_cheapest_start` and `_cheapest_cost` show a priced candidate. |
| Safe default | Native orchestration remains inactive (`shadow`) and both automatic-mode switches remain off. Nothing is started by this guide. |

Suffixes share the `sensor.load_optimizer_1` prefix. Short firmware updates or
interrupted captures may be rejected rather than learned. With power-only
completion detection, the default finish delay is **five low-power scans**, not
a fixed five-minute timer; at the default 60-second interval it is approximately
five minutes. Avoid restarting HA during a learning capture.

Confidence starts low and improves with repeatable completed cycles. It measures
the learned profile, not the probability of a successful remote start. A cost
recommendation is not a queued request. See the
[state explanations](troubleshooting.md#learning-and-recommendations).

Add appliances in **Configure > Appliances and tariff**, retaining existing IDs
so their learning and dashboard references remain associated correctly.

## Optional Next Steps

- [Add a dashboard](dashboard.md). The starter example uses standard cards and
  no charger or appliance-control buttons.
- [Configure a Home Connect dishwasher](dishwasher-control.md), including explicit
  activation and a separately opted-in supervised manual test.
- [Set up advisory EV planning](ev-charging.md). Battery capacity is currently
  supplied by an entity, not a numeric setup field.

## Existing Add-on Installation

Use the [migration guide](migration-addon-to-integration.md), not the empty-install
procedure. Importing a legacy database replaces the integration's learning state.
Do not import old data into an established installation without preserving its
current state. A new installation needs no database import, legacy helpers,
add-on, or migration preparation action.

For faults, follow [troubleshooting](troubleshooting.md) and share only reviewed,
redacted diagnostics. Never attach tokens, private backups or a full HA config.
