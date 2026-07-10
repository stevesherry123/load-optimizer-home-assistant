# Roadmap

This roadmap is the canonical place for planned work, backlog ideas, and future
design notes. Keep released changes in `load_optimizer/CHANGELOG.md` and keep
implementation architecture in `docs/architecture.md`.

## Near-Term Priorities

- improve profile-weighted tariff cost estimation across half-hour slots
- add per-instance earliest start and latest finish constraints
- expose clear recommended start and finish sensors
- expose a recommended-window active state for dashboards and automations
- add a manual recalculation service for tariff, policy, or test changes
- improve runtime status clarity so active capture is obvious

## Scheduling And Cost Estimation

Load Optimizer should remain device-agnostic while improving the user-facing
experience around tariff windows and run recommendations. Community Agile-window
projects show useful patterns, but Load Optimizer should not become Octopus-only
or rely only on fixed-duration appliance assumptions.

Planned scheduling features:

- per-instance earliest start and latest finish constraints
- clear recommended start and finish sensors
- a recommended-window active state for dashboards and automations
- a manual recalculation service for tariff, policy, or test changes
- profile-weighted cost estimation across half-hour tariff slots
- a simple fallback estimator when only runtime and total kWh are known
- a guided Home Assistant configuration flow in a future integration phase

The preferred cost model is profile-weighted. Instead of multiplying total kWh
by an average tariff price, the optimiser should map the learned power profile
onto each candidate tariff window. This matters for long appliance cycles where
most energy is consumed during a small number of heating or charging phases.

Per-instance constraints should support common real-world rules such as:

- only run overnight
- finish before a household wake-up time
- avoid noisy spin phases late at night
- allow opportunistic operation during negative-price windows
- reserve maintenance or high-consumption cycles for special conditions

The project may expose binary sensors later, but the core model should first
publish enough state for either binary sensors or ordinary sensors to be built
on top.

## Inferred Cycle Classification

Some appliances do not expose a selected program or operation state to Home
Assistant. Washing machines connected only through a smart plug are a good
example: the app can see power and energy, but not whether the user selected a
short spin, rinse, cotton wash, eco wash, or maintenance cycle.

Future versions should infer a probable cycle class from the learned power
signature. Useful signals include:

- total runtime
- total energy
- peak power
- number and timing of heating phases
- number and timing of spin-like high-power bursts
- idle gaps or soak periods
- energy distribution across the cycle

The first implementation should stay conservative. A dumb washing machine can
initially learn under `Default`, then later split learned runs into inferred
classes such as `ShortSpin`, `Wash`, `EcoWash`, `Rinse`, or `Maintenance` once
there is enough evidence. Inferred classes should be visible to the user and
remain overrideable through explicit program policies.

For the first washing-machine classifier, expect a small number of practical
classes rather than an exhaustive programme list. The initial target is likely
three broad usage patterns:

- short spin or drain-style cycles
- normal wash cycles
- longer, hotter, or maintenance-style cycles

This classification should support cost estimation as well as recommendation:
two cycles with the same total energy can have very different costs when their
high-power phases land in different tariff windows.

## Runtime Status Clarity

Instance status should distinguish between configuration health and active
capture state. Today `sensor.load_optimizer_N_cycle_state` correctly reports
`running` during a detected cycle, while `sensor.load_optimizer_N_status` can
still report `ready`.

Future versions should expose a clearer instance status such as `capturing`
while preserving separate health and configuration indicators. This will make
live monitoring easier to understand without changing the underlying cycle
state model.

## True Operating Cost

Initial optimisation will use electricity cost only.

Future versions may calculate a broader operating cost incorporating:

- water consumption
- detergent and other consumables
- appliance wear
- battery degradation for applicable devices
- other configurable per-cycle costs

Standing charges should normally be excluded because running a cycle does not
change them.

This broader cost model will be particularly relevant when evaluating negative
electricity prices. Consuming electricity may appear profitable while still
incurring water, consumable, and equipment costs.

## Legacy Retirement

Legacy helper names should remain only long enough to migrate state forward.
After the new model is validated:

- legacy scripts should be removed
- legacy dashboards should be replaced or archived
- legacy helper entities should be deleted

Local tariff-normalising templates, including `sensor.octopus_price_feed_clean`,
should also be decommissioned once Load Optimizer has been validated against the
upstream BottlecapDave Octopus Energy rate event entities directly.
