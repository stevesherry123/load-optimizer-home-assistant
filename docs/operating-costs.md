# Total Cost And Extra-Run Benefit

This describes the unreleased development build. It is not an installed update
or a published release.

## Normal Washing And Extra Runs

A requested normal wash remains useful when it costs money. Its eligible
programmes are compared using total cycle cost and the authorised window.

An opportunistic extra run must have a **strictly positive estimated net benefit**:

```text
Total cost = electricity + consumables + water + wear + other per-run costs
Net benefit = -total cost
```

A 5p electricity credit with 10p of other costs loses 5p and cannot authorise an
extra run. A free cycle with zero other costs breaks even and cannot authorise
an extra run either. Normal requested washing can still use free electricity.

Any positive return qualifies; there is no minimum profit threshold. Eligibility
and ranking use values before display rounding. Decimal arithmetic prevents
exact break-even sums from gaining a tiny apparent credit from binary rounding.

Among currently usable profitable candidates, prefer the **highest net benefit
per run**. Programme priority breaks ties, followed by shorter duration and
programme preference. A usable current opportunity remains ahead of future
opportunities. This ranks individual runs; it does not promise the best possible
sequence of repeated runs across the entire tariff horizon.

Normal washing takes priority. Programme permissions, physical safety checks,
blocked periods, full-cycle prices and run limits still apply. Current prices
and configured costs are checked again before automatic start commands.

## Configure Programme Costs

Add these fields to the programme's existing `program_policies` mapping. Monetary
amounts are in **pence**, except the water price, which is **pence per litre**.

```yaml
program_policies:
  - program: Eco50
    enabled: true
    allow_normal_recommendation: true
    allow_negative_price_run: true
    maximum_runs_per_window: 1
    consumables_cost_pence: 8
    water_litres: 10
    water_cost_pence_per_litre: 0.2
    wear_cost_pence: 1
    fixed_cost_pence: 0
```

This adds 11p to each cycle's electricity cost. Replace the values with your own
estimates. Negative-price permission is separate from controller activation and
the automatic-mode switches.

| Field | Meaning |
| --- | --- |
| `consumables_cost_pence` | Detergent and other consumables per cycle. |
| `water_litres` | Estimated programme water use in litres. |
| `water_cost_pence_per_litre` | Applicable water and wastewater price per litre. |
| `wear_cost_pence` | Your estimated wear allowance per cycle. |
| `fixed_cost_pence` | Other per-cycle costs not already included above. |

The older `estimated_overhead_cost_pence` remains an alias for `fixed_cost_pence`.
If both are supplied, `fixed_cost_pence` takes precedence; they are not added
together. If existing overhead already includes detergent, remove that part
before entering a separate consumables cost.

Omitted operating costs count as zero and remain listed as **unconfigured**.
An explicit zero marks a field as configured. Negative, nonnumeric and non-finite
cost inputs are rejected. Missing electricity prices never count as zero.

## Review The Estimate

The full and beta dashboard templates include a **Cycle costs** card for normal
overnight washing and profitable extra runs. It shows electricity, consumables,
water, wear, other costs, the total and any unconfigured assumptions. Positive
benefits below 0.01p are labelled as such rather than displayed as zero.

Recommendation attributes expose `net_benefit_pence`, `positive_net_benefit`,
`unconfigured_costs` and `operating_cost_breakdown`. These are planning estimates,
not actual supplier billing or realised profit. `no_positive_net_benefit` records
the absence of a profitable extra run without issuing a routine notification or
altering permission for normal washing.
