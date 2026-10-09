# Load Optimizer

Plan appliance cycles and EV charging around your electricity tariff using
existing Home Assistant entities. Learn when an appliance uses energy during a
cycle, compare running costs, and find suitable low-cost or negative-price windows.

## Stable Features

- **Appliance learning:** capture completed cycles from power and energy sensors,
  retain learned programme profiles, and estimate costs across tariff periods.
- **Scheduling recommendations:** compare programmes and start windows using
  configured deadlines, programme policies and automatic cooldowns.
- **Optional dishwasher controls:** opt into compatible remote-start services
  with connection, door and already-running safety checks. Manual programme
  requests bypass automatic cooldowns, not physical safety checks.
- **EV charging plans:** use battery percentage, usable capacity, target, charge
  power and efficiency to select charging windows and estimate cost or profit.
- **Ofgem comparison:** choose a GB electricity region and payment method for a
  daily cached, effective-dated default-tariff unit-rate benchmark.
- **Optional dashboards:** a standard-card template, plus a richer chart example
  with tariff-local time, 24/48-hour coverage, benchmark and current-time markers.

EV charging is **advisory**: Load Optimizer does not switch a charger or power
plug. Installing the integration does not enable automatic appliance starting.
Your existing tariff, appliance and vehicle integrations remain required.

## HACS Installation

Until this repository is included as a default HACS repository, add it as a
custom repository:

```text
https://github.com/stevesherry123/load-optimizer-home-assistant
```

Choose category **Integration**, install **Load Optimizer**, restart Home
Assistant, then add **Load Optimizer** from Settings > Devices & services.

Choose the latest **stable GitHub release**, not a development branch. The
HACS catalogue request is [#11744](https://github.com/hacs/default/pull/11744);
submission is not acceptance. Once accepted and scanned, users can find the
integration directly in HACS without adding a custom repository.

Home Assistant **2024.12 or later** is required. The Ofgem benchmark is for
Great Britain; other supplier integrations can supply compatible tariff data.
No Octopus API token, separate app, or AI subscription is required.

Start with the [setup guide](docs/getting-started.md). Configure one
learned-appliance hub containing all your appliance instances; EV planning uses
separate entries. Existing settings can be edited through the integration's
**Configure** cog, including EV settings without recreating the entry.

## Add-on Migration

To migrate the existing add-on, create a Load Optimizer integration entry with
load type `learned_appliance`, paste your existing add-on `instances_yaml` and
tariff settings, then import the old `/data/load_optimizer.json` database with
the `load_optimizer.import_legacy_state` service.

See the [migration guide](docs/migration-addon-to-integration.md). Stop the old
add-on before activating the integration so two runtimes cannot capture or
control the same appliance concurrently. Keep its database and backup until
the imported counts and a new complete cycle are verified.

The old add-on distribution is retired. Do not add this repository to the
Home Assistant add-on store. The compatibility engine and explicit administrator
import action remain available for migration; ordinary new installations need
no legacy database.

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

## Updates And Betas

Normal users are offered stable GitHub releases. Pushing a branch, merging to
`main`, or creating a tag alone does not publish a new stable update.
Beta testers explicitly enable prereleases in HACS. Update installation is a
user action unless they have configured their own automatic-update automation;
integration code changes require a Home Assistant restart to take effect.

Tariff history, historical analysis, portable history import and optional AI
summaries remain **experimental beta features**, not stable functionality.
Public development branches can be inspected by anyone, even though they are not
offered as normal stable updates. Do not enable beta updates on an installation
that must remain on stable.

See [release channels and publication](docs/release-channels.md) for the exact
workflow, notification process and limitations of download/installation counts.

## Known Limitations

- EV charging is advisory, not a built-in charger switch controller.
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

For a suspected vulnerability, use the private reporting route in
[SECURITY.md](SECURITY.md), not a public issue. See
[data handling and privacy](docs/privacy.md) before sharing logs, dashboard
screenshots or older diagnostic downloads. The integration adds no telemetry.

The [publication checklist](docs/hacs-publication.md) distinguishes custom
repository installation from inclusion in HACS's default catalogue.

## Documentation

The README is the front door, not the entire manual. HACS displays versioned
README content; release notes describe each update, and the linked guides
provide setup and troubleshooting detail.

- [Installation and configuration](docs/getting-started.md)
- [Dashboards, manual starts and scheduling explanations](docs/dashboard.md)
- [Migration from the retired add-on](docs/migration-addon-to-integration.md)
- [Release channels, HACS acceptance and statistics](docs/release-channels.md)
- [Changelog](CHANGELOG.md) and [GitHub releases](https://github.com/stevesherry123/load-optimizer-home-assistant/releases)
- [Privacy](docs/privacy.md) and [private vulnerability reporting](SECURITY.md)
- [Contributing](CONTRIBUTING.md), [architecture](docs/architecture.md) and [roadmap](docs/roadmap.md)

Older design documents are historical proposals, not promises of released
features. Use this README, the setup guide and the notes for your installed
release when configuring the integration.
The retired add-on and orchestration packages are no longer distributed; all
supported learning, scheduling, recovery, and appliance controls live in the
integration.
