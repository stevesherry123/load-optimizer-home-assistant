# Roadmap

This roadmap is the canonical place for planned work, backlog ideas, and future
design notes. Keep released changes in `load_optimizer/CHANGELOG.md` and keep
implementation architecture in `docs/architecture.md`.

## Near-Term Priorities

- improve profile-weighted tariff cost estimation across half-hour slots
- add per-instance earliest start and latest finish constraints
- extend helper-driven deadline support for calendar and travel-aware scheduling
- add selectable scheduling strategies such as `cheapest_earliest_finish` and
  `cheapest_latest_finish`
- continue refining daytime and overnight scheduling windows
- expose clear recommended start and finish sensors
- expose a recommended-window active state for dashboards and automations
- add a manual recalculation service for tariff, policy, or test changes
- improve runtime status clarity so active capture is obvious
- model additional per-cycle operating costs such as detergent, water, and
  appliance wear
- account for household solar generation and battery storage when estimating the
  effective cost of running a cycle
- add automatic negative-price opportunity handling for programs explicitly
  allowed by policy

## Scheduling And Cost Estimation

Load Optimizer should remain device-agnostic while improving the user-facing
experience around tariff windows and run recommendations. Community Agile-window
projects show useful patterns, but Load Optimizer should not become Octopus-only
or rely only on fixed-duration appliance assumptions.

Planned scheduling features:

- per-instance earliest start and latest finish constraints
- helper-driven deadline support via Home Assistant input helpers
- optional calendar integration, with TripIt recommended for travel-aware
  scheduling where users already expose TripIt to Home Assistant
- scheduling strategies that are separate from constraints:
  `cheapest_earliest_finish`, `cheapest_latest_finish`, and later `cheapest_absolute`
- schedule window preferences for overnight/daytime operation
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

Scheduling strategies should rank only the candidates left after constraints are
applied. A deadline answers "what is allowed"; a strategy answers "which allowed
slot is preferred." For example, a dishwasher before work travel may use a
calendar-derived deadline with `cheapest_earliest_finish`, while an EV may use a
departure deadline with `cheapest_latest_finish`.

Calendar integration should be optional for basic operation but recommended for
full automation. The first implementation should prefer a helper contract such
as an enabled flag plus a must-finish-by datetime, so TripIt, Google Calendar,
Outlook, or manual Home Assistant automations can all drive the same scheduler.
Direct calendar polling can be added later as a convenience layer.

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
- water disposal or sewerage charges where applicable
- detergent and other consumables
- appliance wear
- battery degradation for applicable devices
- other configurable per-cycle costs

These costs should be configurable per program policy. Examples include a fixed
dishwasher tablet cost, a pence-per-litre water cost, an estimated litres-per-run
value, and a depreciation or wear allowance. Energy-only recommendations can
remain available, but the broader model should support a true operating cost and
show energy cost separately from non-energy costs.

Standing charges should normally be excluded because running a cycle does not
change them.

This broader cost model will be particularly relevant when evaluating negative
electricity prices. Consuming electricity may appear profitable while still
incurring water, consumable, and equipment costs.

Future versions should also support local energy context. For homes with solar
panels, battery storage, or both, the cheapest grid-import slot may not be the
true cheapest operating slot. The optimiser should eventually be able to factor
in available solar generation, battery state of charge, charge/discharge limits,
round-trip efficiency, export value, and whether stored energy should be
reserved for other household loads. The first version of this should be
optional, sensor-driven, and supplier-agnostic.

Negative-price automation should remain opt-in per program. When electricity is
negative, the optimiser should prefer useful, high-consumption, short-duration
programs that are explicitly marked as eligible, while respecting cooldowns,
maintenance limits, and any future additional operating-cost model.

## Completed Appliance Infrastructure Cleanup

The retired local appliance packages, templates, helper definitions, dashboards,
and Pyscript files have been removed from this repository. Future work should
continue to keep the public project focused on the installable App runtime.

Energy-provider helper layers are a separate integration concern. They should be
reviewed independently from the appliance cleanup so useful Octopus or tariff
logic is not removed accidentally.
