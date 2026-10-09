# EV Options Beta

Branch: `beta/ev-options-v1.5.2`, updated from stable main for v1.5.5-beta.1
acceptance and v1.5.5 stable promotion.
It does not include or promote the v1.6/v1.7 tariff-intelligence branches.
The editor is now merged and released in v1.5.5, retained in v1.5.6. The latter
adds minimum-HA appliance device-link compatibility and expands actual registry
acceptance; 209 stable unit tests pass. Use v1.5.6 for public installation.

Implemented: the EV entry's Configure menu offers EV charging settings and
Price-cap benchmark. Setup and editing share one schema. Saved options override
setup values; optional target/connection references and the ready-by deadline
can be cleared, including references originally saved in entry data.
Required entities, charge power, fallback target, efficiency and slot length
are prefilled. Ready by is a daily local `HH:MM` deadline, not an ISO datetime.
Saving does not replace the entry, reset learning or enable charger control.

204 unit tests pass locally. The minimum-HA import/schema job checks actual
Home Assistant selectors, retained numeric defaults, optional-reference clearing
and rejected numeric/deadline values. It also serializes the form exactly as
Home Assistant's API does, catching unsupported validators before publication.

## Isolated Acceptance (9 October 2026)

- Real Home Assistant 2024.12 setup created a synthetic EV entry and nine native
  entities. No production configuration, appliance or learning store was copied.
- The browser showed EV charging settings and Price-cap benchmark only. Required
  references and numeric values were prefilled; cleared optional references stayed
  empty. Invalid `25:00` reported a field error, and a valid save succeeded.
- Actual options listeners reloaded the coordinator. Target/power changes affected
  the advisory plan; independent benchmark edits retained EV settings.
- Entry data, entry ID, device ID and all nine entity IDs survived reload, fresh
  process restart, actual downgrade to unchanged v1.5.4 code and re-upgrade.
- EV entries expose no switch/button control; no charger service was called.
- An older unset-description-name issue was corrected without renaming registered
  entities. The deadline form-serialization bug found during acceptance is fixed.

The real lifecycle test is `tests/ha_ev_lifecycle_smoke.py`, run separately with
the minimum HA dependencies in CI. Its optional `--serve` switch exposes a
loopback-only test UI, using synthetic sources and a development-only login.
Never point this harness at an existing Home Assistant configuration: it refuses
nonempty directories unless they contain its synthetic acceptance snapshot.

The owner's v1.7 installation and queued dishwasher run were not reloaded or
restarted for these tests. Production installation remains a separate operation
after active/queued appliance work is complete. The owner's queued MixedLoad wash
subsequently completed normally; the publication learning gate is now satisfied.

## Live Acceptance Before Promotion

1. On a dedicated beta installation, record the EV entry/entity identities,
   options and current advisory plan. Do not replace the owner's v1.7 deployment
   with this older feature branch merely to test an options editor.
2. Open Configure on an EV entry; confirm only EV and benchmark sections appear.
3. Change target/power and benchmark independently. Confirm each section retains
   the other's values and updates the plan after the existing reload listener.
4. Clear optional references, including ones originally in entry data. Confirm
   the numeric fallback target and cleared local deadline take effect.
5. Reload/restart and confirm entry and entity IDs, options and advisory behavior.
6. Confirm learned-appliance options and stored learning are unchanged. Test a
   downgrade with the new options present; options must not enable control.

The isolated acceptance and merge gates above are complete. Propagate the editor
into the analysis/import branches without discarding their independently verified
history stores; this remains separate from promoting analysis to stable.

## Owner Beta Deployment (9 October 2026)

Installed v1.7.0-beta.4 after the wash completed and fresh checks confirmed idle
appliances, no queued request and zero active captures. After one restart, all
222 registered entity/device identities and the dashboard configuration matched
their pre-update snapshot. Learning totals remain 114 / 189 / 46, MixedLoad
4 runs at 61%, and schema-2 tariff history retains 91 days with no storage error.
All three appliance forecasts are ready and focused integration logs are clean.
The real EV Configure API opens only EV and benchmark sections, serializes the
form and supplies saved required defaults. It was cancelled without saving any
production settings. EV entities remain advisory with no button or switch.
Independent one-to-four-hour tariff-window arithmetic still matches.
