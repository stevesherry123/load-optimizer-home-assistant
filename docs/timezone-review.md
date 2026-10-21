# HACS Timezone Review, v1.5.8

This stable patch addresses HACS default submission #11744, review by Frenck on
21 October 2026. It is based on v1.5.7 and does not include beta/EV-control work.

## Fix And Audit

- `async_setup_entry` awaits Home Assistant's `dt_util.async_get_time_zone` once
  for the configured tariff timezone. Invalid names fail before the coordinator
  starts. Reloading changed options resolves the new timezone at setup again.
- The coordinator retains the resulting `tzinfo` and passes it to
  `PriceCapManager.async_status`. Current local date, cached retrieval date and
  effective-period UTC boundaries all reuse that object. Price-cap serving no
  longer imports or constructs `ZoneInfo`.
- Native overnight scheduling uses `dt_util.as_local`, reusing HA's configured
  default timezone rather than constructing it during scheduling/explanation.
- EV form validation, tariff parsing and ready-by conversion run as executor
  jobs. Their synchronous standalone helpers may still resolve named zones,
  but those calls do not run on HA's event loop.
- Before legacy appliance calculations, the HA adapter asynchronously resolves
  configured tariff zones and the UTC/London defaults, retaining strong object
  references. The existing synchronous calculation helpers then use ZoneInfo's
  cached objects instead of cold timezone-database reads. Invalid configured
  names fail closed rather than silently selecting another timezone.

The audit covers every `ZoneInfo` construction in this stable component tree.
It does not claim that this timezone fix constitutes a full integration review.

## Regression Checks

- A cleared-cache, uncommon timezone resolves once off the event-loop thread
  during entry setup; an invalid resolution never starts the coordinator.
- Price-cap serving is exercised with synchronous ZoneInfo construction patched
  to fail, ensuring it uses the supplied object instead.
- UTC midnight within one local date reuses the daily cache; local midnight
  within one UTC date refreshes it.
- London spring and autumn effective-period boundaries span 23 and 25 hours;
  both instances of the repeated autumn hour share the same daily cache.
- A synthetic appliance scan resolves and retains its configured timezone before
  running calculations with cold timezone-file reads forbidden.
- Existing unit, import, dashboard, EV lifecycle and security acceptance remain
  required. The timezone regression runs on the declared HA 2024.12 minimum and
  has also been run against HA 2026.10.2 locally. No physical loads are used.

Run the focused acceptance check with:

```sh
python tests/ha_timezone_smoke.py
```
