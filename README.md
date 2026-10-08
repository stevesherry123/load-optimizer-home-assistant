# Load Optimizer


Load Optimizer is a Home Assistant integration for scheduling flexible
electrical loads around dynamic tariffs, deadlines, and negative-price windows.

It is designed to be device-agnostic. Dishwashers, washing machines, EVs, home
batteries, immersion heaters, and future load types should be handled as
adapters on top of one shared optimisation core.

## HACS Integration

Load Optimizer moved from the original Home Assistant add-on to a HACS custom
integration. The integration is now the sole supported installation path.

The integration supports two setup paths:

- **Learned appliances**: learns power profiles from completed cycles and
  publishes profile-weighted running costs and scheduling recommendations.
  Existing add-on users can import their learning database without changing
  the `sensor.load_optimizer_*` entity IDs.
- **EV charging**: reads an existing battery percentage entity, battery capacity
  entity, target percentage, charger power, and future tariff entity, then
  publishes the cheapest charging windows required to reach the target.

EV charging remains advisory: the integration publishes a charging plan for a
household-owned automation or charger integration to follow. Learned appliances
can optionally use Load Optimizer's native orchestration controls after their
start service and safety checks are configured.

### HACS Installation

Until this repository is included as a default HACS repository, add it as a
custom repository:

```text
https://github.com/stevesherry123/load-optimizer-home-assistant
```

Choose category **Integration**, install **Load Optimizer**, restart Home
Assistant, then add **Load Optimizer** from Settings > Devices & services.

For public/stable installs, use tagged releases. The HACS metadata hides the
default branch so ordinary users are not nudged toward development builds.

Home Assistant **2024.12 or later** is required. The Ofgem benchmark is for
Great Britain; other supplier integrations can supply compatible tariff data.
No Octopus API token, separate app, or AI subscription is required.

Start with the [new-installation guide](docs/getting-started.md). Installation
does not enable automatic physical control. Configure one learned-appliance
hub containing all your appliance instances; EV planning uses separate entries.

### Add-on Migration

To migrate the existing add-on, create a Load Optimizer integration entry with
load type `learned_appliance`, paste your existing add-on `instances_yaml` and
tariff settings, then import the old `/data/load_optimizer.json` database with
the `load_optimizer.import_legacy_state` service.

See the [migration guide](docs/migration-addon-to-integration.md). Stop the old
add-on before activating the integration so two runtimes cannot capture or
control the same appliance concurrently. Keep its database and backup until
the imported counts and a new complete cycle are verified.

### EV Entities

For a Volvo-style setup, the config flow can use entities such as:

- `sensor.volvo_xc60_battery`
- `sensor.volvo_xc60_battery_capacity`
- `sensor.volvo_xc60_target_battery_charge_level`
- `sensor.volvo_xc60_charging_connection_status`

The tariff entity can be any Home Assistant entity exposing future rates in one
of the formats already supported by the original Load Optimizer tariff parser,
including `ai_feed`, `rates`, `prices`, `forecast`, or `all_rates`.

## Retired Legacy Add-on

The Home Assistant add-on distribution was retired in v1.2 after configuration,
learning history, tariff processing, and persisted-storage migration were
validated against the HACS integration.

Do not add this repository to the Home Assistant add-on store. Existing add-on
users should take a backup, import `/data/load_optimizer.json`, confirm the
learned run counts after an integration reload, and then uninstall the stopped
add-on. The add-on-only backup should be retained until the integration has
captured another complete cycle.

The compatibility engine and explicit import service remain in the integration
for users migrating older installations.

## Optional Dashboard

The HACS installation includes an optional dashboard template covering
integration health, appliance plans, EV charging, and learned-cycle data. It is
not automatically added to your sidebar and its example entity IDs must match
your installation. See
[`docs/dashboard.md`](docs/dashboard.md) for the short installation step.

Version 1.5 adds an effective-dated Ofgem default-tariff benchmark. Choose the
electricity region and payment method in the integration setup or options. Load
Optimizer checks Ofgem's official tables daily, caches the last validated
value, and exposes it as a native sensor for the tariff chart. This is a
comparison benchmark, not a price limit on dynamic tariffs such as Agile.

## Goals

- Schedule flexible electrical loads from normalized tariff data.
- Keep supplier integrations optional and provider-neutral.
- Publish advisory entities that Home Assistant automations can safely consume.
- Retain the learned appliance-cycle engine during the integration migration.
- Add EV charging as the first v1.0 integration load type.

## Design Principles

- Use a shared core for tariff parsing and optimisation.
- Treat each load as a configured Home Assistant integration entry.
- Keep device-specific logic in adapters only.
- Keep physical control opt-in and household-owned.

## Naming Convention

The legacy add-on uses the instance-based namespace:

- `load_optimizer_1_*` for the first appliance instance
- `load_optimizer_2_*` for the second appliance instance
- future adapters can map their own device-specific sensors into the same shared model

For each configured add-on instance, the add-on publishes examples such as:

- `sensor.load_optimizer_N_status`
- `sensor.load_optimizer_N_power`
- `sensor.load_optimizer_N_energy`
- `sensor.load_optimizer_N_cycle_state`
- `sensor.load_optimizer_N_last_runtime`
- `sensor.load_optimizer_N_last_energy`
- `sensor.load_optimizer_N_last_profile`
- `sensor.load_optimizer_N_learned_programs`
- `sensor.load_optimizer_N_program_model`
- `sensor.load_optimizer_N_program_policies`
- `sensor.load_optimizer_N_cost_status`
- `sensor.load_optimizer_N_cheapest_start`
- `sensor.load_optimizer_N_cheapest_cost`
- `sensor.load_optimizer_N_recommended_program`

The v1.0 integration creates entities under the normal Home Assistant integration
device model, such as:

- `sensor.<name>_status`
- `sensor.<name>_estimated_cost`
- `sensor.<name>_estimated_profit`
- `sensor.<name>_needed_battery_energy`
- `sensor.<name>_wall_energy`
- `sensor.<name>_next_slot_start`
- `binary_sensor.<name>_charge_now`
- `binary_sensor.<name>_ready_to_charge`

## Current Scope

The current integration scope is:

- HACS-compatible custom integration structure.
- UI configuration flow.
- EV charging slot planning from existing Home Assistant entities.
- Tariff parsing inherited from the original add-on core.
- Cost and profit estimates for selected charging windows.
- Binary advisory state for EV "charge now".
- Opt-in native learned-appliance scheduling, safety checks, and start controls.

The learned-appliance runtime is the supported path for migrated add-on
installations. Uninstall the stopped add-on after validating the imported
learning counts and taking a backup.

## Roadmap

Planned work and remaining gaps are tracked in [the roadmap](docs/roadmap.md).
Stable v1.5.x includes appliance learning, opt-in orchestration, advisory EV
planning and the regional price-cap benchmark. Tariff history, historical
analysis, import and optional AI summaries are separate **v1.6/v1.7 betas**;
they are not features of the stable publication release.

## Known Limitations

- EV charging is advisory, not a built-in charger switch controller. In the
  stable release, EV configuration cannot yet be edited through its options cog.
- Appliance setup uses YAML definitions; a fully guided appliance editor is
  planned. Only one learned-appliance hub is supported.
- The packaged dashboard is a standard-card template. The richer tariff-chart
  example requires ApexCharts Card and installation-specific entity edits.
- Ofgem is a comparison benchmark, not a ceiling on Agile prices. Select the
  electricity region used by your meter's tariff, not a general geographic label.
- Home Assistant unavailable/unknown states and incomplete future tariffs can
  leave a recommendation waiting. Do not turn missing data into a start command.

## Support And Development

Report faults with the release number, Home Assistant version and redacted
diagnostics in [GitHub Issues](https://github.com/stevesherry123/load-optimizer-home-assistant/issues).
Never post access tokens or a full private configuration. See the
[contribution guide](CONTRIBUTING.md) for release-channel and testing rules.

The [publication checklist](docs/hacs-publication.md) distinguishes custom
repository installation from inclusion in HACS's default catalogue.

## Repository Layout

```text
.
├── README.md
├── hacs.json
├── custom_components/
│   └── load_optimizer/
├── CHANGELOG.md
├── homeassistant/
│   ├── dashboards/
│   └── packages/
├── docs/
│   ├── architecture.md
│   ├── naming.md
│   └── roadmap.md
└── tests/
```

## Public-State Model

The shared state model should focus on:

- active cycle status
- current program or mode
- cycle start timestamp
- start energy reading
- live profile samples
- peak power
- last completed cycle data
- learned aggregate database
- human-readable summary

## Project Status

The HACS integration is the supported product and development line. The legacy
add-on packaging has been removed after successful migration validation.

Optional dashboard and travel-deadline examples are stored in `homeassistant/`.
The retired add-on and orchestration packages are no longer distributed; all
supported learning, scheduling, recovery, and appliance controls live in the
integration.
