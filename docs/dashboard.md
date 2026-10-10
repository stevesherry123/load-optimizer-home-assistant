# Optional Dashboard

## Start With One Appliance

For the [new-install guide](getting-started.md), start with
[`examples/one-appliance-dashboard.yaml`](examples/one-appliance-dashboard.yaml).
It contains only learning and recommendation sensors for appliance ID `1`:
no Volvo entities, additional appliances, custom cards or physical-control buttons.
Change the `load_optimizer_1_` prefix if using a different appliance ID.

Create an empty dashboard in **Settings > Dashboards**, open it in edit mode,
then use its **Raw configuration editor** to paste the example's contents. Use
a new dashboard, not the raw editor of an existing dashboard you want to keep.
The dashboard is stored in your HA configuration and HACS will not overwrite it.
Its contents are YAML even though this is called a storage-mode dashboard.

Before learning a complete cycle, cost and programme values can be unknown or
waiting. That is different from an entity-not-found error. See
[troubleshooting](troubleshooting.md). This small dashboard intentionally has no
price graph; the richer chart example below is a separate optional installation.

## Larger Dashboard Template

The HACS package includes a standard Lovelace YAML dashboard at:

```text
/config/custom_components/load_optimizer/dashboard.yaml
```

The integration does not automatically add a sidebar dashboard. For a YAML-mode
dashboard, first place your customised copy outside `custom_components/`, for
example at `/config/dashboards/load_optimizer.yaml`. HACS replaces files under
`custom_components/load_optimizer/` during updates; do not edit the packaged
file in place. Create the destination directory if needed.

Merge the following into the existing `lovelace:` section of `configuration.yaml`,
without adding duplicate top-level keys or discarding other dashboard entries:

```yaml
lovelace:
  mode: storage
  dashboards:
    load-optimizer:
      mode: yaml
      title: Load Optimizer
      icon: mdi:home-lightning-bolt-outline
      show_in_sidebar: true
      filename: dashboards/load_optimizer.yaml
```

The dashboard is a template, not automatic entity discovery. It uses only
standard Home Assistant cards and integration entities. The examples assume
appliance IDs 1, 2 and 3 and a Volvo-titled EV entry. Remove views/cards for loads
you do not have and replace EV entity IDs with those shown on your EV device.
Optional diagnostic entities may be disabled or unpublished in your settings.

Check configuration before restarting HA to register a new YAML-mode dashboard.
Alternatively, paste the template into a new storage-mode dashboard's raw editor
as above. Neither method deletes or replaces your existing dashboards. Your copy
does not automatically acquire later template improvements; review and adopt
those separately rather than overwriting local customisations.

## Automatic Scheduling Explanation

The Overview and Appliances views include an Automatic Scheduling card in the
full and standard templates respectively. It separates a candidate recommendation
from a saved start request: a ready programme is not a promise that a wash will
start. It shows the queued programme/time, last automatic request, actual start
attempt, learning confidence, outstanding safety checks and recent decisions.

`sensor.load_optimizer_1_automation_explanation` supplies the reasons from the
native scheduler, rather than reproducing the scheduling rules in dashboard
templates. An already-used overnight reservation is amber, not green. Scheduling
events are bounded to the most recent 20 and stored with the native controls,
so diagnosis does not depend on Recorder being enabled for optimizer sensors.
Existing history is not reconstructed or guessed during an upgrade.

Dates use Home Assistant's configured home timezone, including its timezone
abbreviation, even when the dashboard is opened while travelling. The card falls
back to the existing queue and attempt records on older integration versions.
It does not start, cancel or re-arm a wash. The new sensor and durable reasons
require the scheduling-diagnostics update; adding the card alone does not fix
older scheduling behaviour.

Manufacturer updates can produce short power captures. A rejected capture without
a newly learned wash or an observed Bosch running operation must not confirm a
wash or cancel its pending overnight request. A real observed wash may still
complete without entering learning, for example if its capture was interrupted.
Startup, forecasts and programme selection were verified live on 9 October.
A subsequent real MixedLoad wash completed with its learning increment
confirmed, passing the physical-cycle publication gate. These checks cover the
owner's appliance, not every model; unfamiliar installations should verify a
completed learned cycle before enabling automatic control.

## Manual Programme Selection

The override dropdown follows the configured dishwasher's live programme selector,
with its last known options retained while the appliance is unavailable. It is
not restricted by learning confidence or automatic programme cooldowns.

Select a programme such as MixedLoad, then press **Start Selected Program Now**
to request it immediately. Explicit manual starts work even without a ready cost
recommendation. Scheduled selected-programme requests use manual candidate windows
when available, without automatic cooldown filtering. Normal connection, closed
door, remote-start and already-running checks still apply. The automatic engine
retains its existing cooldowns; manual requests do not silently re-arm automation.

## Current Price Colours

The current import-price tile optionally uses
[card-mod](https://github.com/thomasloven/lovelace-card-mod), installed through
HACS as a dashboard resource, using a release compatible with your HA version.
Its background is light green below the regional
Ofgem benchmark, light yellow when equal, and red above it. Comparisons use
two decimal places in p/kWh so visually equal prices are not marked higher or
lower because of hidden precision. Missing, unavailable or non-finite values
keep the normal neutral background. Both source entities are watched, so a
tariff update or a new benchmark changes the colour without a reload.

The Ofgem tile remains neutral. Without card-mod, both tiles remain usable
standard Home Assistant tiles, but comparison colouring is not applied. This
optional styling does not affect scheduling, learning or the daily benchmark
lookup, and does not require a Home Assistant restart.

The richer example dashboards under `homeassistant/dashboards/` use
`apexcharts-card`. Their future-price axes are formatted in the tariff timezone
published by Load Optimizer, not the viewing browser's timezone. This keeps the
tariff-day view aligned when opened while travelling. It shows today's 24 hours
until next-day data arrives, then today and tomorrow across 48 hours. The Ofgem
benchmark and Now lines use the same tariff-local time basis. These richer
examples are not automatically installed by HACS.
