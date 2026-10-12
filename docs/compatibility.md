# Compatibility And Scope

A recommendation and a physical start command are separate capabilities.

| Capability | Current stable support | Prerequisites / limits |
| --- | --- | --- |
| Appliance learning | Generic appliances with measurable cycles | Numeric power in W; cumulative energy in kWh recommended. Programme and operation-state sources optional. |
| Appliance recommendations | Learned profiles plus compatible future tariffs | Explicit eligible programme policies, complete prices and configured constraints. One hub contains all appliances. |
| Native dishwasher starting | Home Connect / Bosch-style controls | Currently appliance ID `1` only, all control references, activation and physical safety checks. Not a generic start-service adapter. |
| Washing machine / vacuum starting | Not built in | Learning does not imply a manufacturer-specific controller. |
| EV planning | Advisory slots and cost estimates | Battery percentage and usable-capacity entities, charge power and future tariffs. Does not switch a charger or plug. |
| Ofgem benchmark | Great Britain regional default-tariff electricity unit rate | Region and payment method configured separately. Not a dynamic-tariff cap or a complete bill comparison. |
| Dashboards | Optional templates | Not added automatically. Rich charts require ApexCharts Card; price colouring optionally requires card-mod. |
| Historical analysis / import / AI summaries | Experimental tariff beta only | Not stable features. AI is not required for learning or scheduling. |

Home Assistant 2024.12 or later is the declared minimum. Automated checks use
that version, but do not certify every HA release or appliance model. The owner's
successful Home Connect wash is evidence for that installation, not universal
manufacturer compatibility. Community reports should include HA and integration
versions and whether learning, recommendations or starting was tested, without
private device identifiers.

## Sources

- BottlecapDave Octopus current-day and next-day rates events supply future
  prices. Their `value_inc_vat` values use `gbp_per_kwh`.
- Other providers can supply compatible structured attributes (`rates`, `prices`,
  `forecast`, `all_rates`) or supported `ai_feed` data. A numeric current price
  alone is not a forecast. Verify current price and coverage before relying on it.
- A monitoring plug can measure an appliance. Turning on mains power is not a
  substitute for a supported and verified remote-start command.
- EV setup currently requires a `sensor` for capacity and optional connection
  status. See [EV planning](ev-charging.md) for constant-capacity and binary-status
  adapters; do not pass raw `on`/`off` as a connection status.

Use [getting started](getting-started.md) for new installations and the separate
[migration guide](migration-addon-to-integration.md) for legacy add-on data.
