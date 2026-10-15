# History Import And Optional Narrative (Development Only)

Current branch: `beta/next`. Installed test release: `v1.7.0-beta.7`, verified
on 14 October 2026. Published stable release: `v1.5.7`; analysis/import/AI remain
unpromoted. The old stacked tariff branches were consolidated and retired;
their commits and release tags remain available. See [release channels](release-channels.md).

The approved 90-day official Octopus backfill and subsequent live history are
preserved. The dated acceptance records below describe what was verified then,
not the current release or an authorization for another import/provider call.

## Portable Import

Use a JSON export from `load_optimizer.export_tariff_history`. The format is:

```json
{
  "schema": 1,
  "source_id": "<matching source_id from the destination analysis status attributes>",
  "timezone": "Europe/London",
  "price_unit": "p_per_kwh",
  "days": [
    {"date": "2026-10-07", "slots": [
      {"start": "2026-10-06T23:00:00Z", "end": "2026-10-06T23:30:00Z", "price_p_per_kwh": 20.0}
    ]}
  ]
}
```

The example intentionally omits the remaining slots for brevity; actual import
requires complete contiguous coverage of every local day. DST days may have
46 or 50 half-hour slots. Units and timezone must match; timestamps require
explicit offsets; non-finite/boolean prices and conflicting duplicates fail.

Imports also require an exact matching `source_id`. This identifier binds the
file to the configured tariff entity set, timezone and input price unit; timezone
alone does not distinguish tariffs or electricity regions. Export from this
branch includes the identifier automatically. Older exports without it fail
validation. An adapter for another installation or the old application must
verify the actual tariff/region before mapping its data to the destination
identifier; do not simply add or replace an identifier to bypass that check.

`load_optimizer.import_tariff_history` accepts `entry_id`, `history_json`,
`dry_run` (default true), `overwrite_live` (default false), and `retention_days`
(default 90, max 365). The service response counts imported, replaced, skipped,
blocked-live and outside-retention days. All rows are validated before any
write. Malformed files fail as a whole without partially updating storage.
Current/future days are excluded. Valid import writes atomically and records
provenance; subsequent live observations take precedence over imported data.

Identical retries do not rewrite history. Failed writes leave memory untouched.
An existing Octopus Intelligence CSV/JSON needs an explicit adapter based on
its actual schema, timezone and units; do not rename it and assume compatibility.
The implemented `agile_buddy` adapter accepts the old app's JSON list of
`{"dt": "...Z", "r": 20.0}` records: `dt` is the half-hour period END and
`r` is p/kWh. Set `format: agile_buddy` and supply `history_tariff_code` verified
from the cache's original source. It must exactly match the tariff codes on all
configured destination rate entities. A filename or geographic label is not
verification. The adapter does not download history or infer missing metadata.
Incomplete days are reported and excluded rather than padded. Invalid records
or conflicting duplicate prices reject the entire conversion. JSON input is
limited to 16 MiB and parsing/conversion runs off Home Assistant's event loop.
No external source download or redistribution rights are assumed.

### Rollback Safety

Provenance-aware history uses a separate `tariff_history_v2` store with schema 2.
On first load, valid schema-1 history is copied into it without modifying the
original. Failed migration preserves the original and disables history writes.
Missing provenance in schema 2 is treated as corruption, not guessed as live.

Older releases continue using the original schema-1 store. They cannot erase
the new imported history or its provenance. While rolled back, their historical
analysis does not see the new imports; upgrading again restores the schema-2
history. Once schema 2 exists, schema-1 changes made during rollback are not
automatically merged: live rates recapture available days, but older days seen
only during rollback need a verified import. Appliance learning is unaffected.

## Optional Narrative

The following describes tested, unreleased `beta/next` behavior. Installed
beta.7 still requires a complete next calendar day. The
[published forecast coverage plan](forecast-coverage-plan.md) records acceptance
of explicitly scoped partial-day summaries without waiting for the trailing
hour. Strict historical-day import validation is unaffected.

`load_optimizer.generate_tariff_summary` accepts `entry_id` and an explicit
`ai_task_entity`. It uses Home Assistant's `ai_task.generate_data` action:
https://www.home-assistant.io/actions/ai_task.generate_data/

AI is disabled by default and never called by the coordinator or a timer.
An explicit service call may incur costs through the selected provider.
No API key is configured in Load Optimizer. AI Task availability is checked at
runtime, so older Home Assistant versions without it retain deterministic
analysis without optional narrative.

Only an allowlisted compact analysis is sent, without entity IDs, credentials,
raw history or storage metadata. A validated contiguous forecast from midnight
through at least 19:00 tariff-local time can generate a scoped narrative;
historical warm-up must be disclosed when applicable. Missing prefixes, internal gaps and unhealthy
sources/storage block generation. Coverage and unknown trailing prices are
explicit in the provider input. Provider failures, malformed responses and a 60-second timeout
are independent of scheduling and learning. Concurrent duplicate requests do
not cause concurrent provider calls. Status is disabled/pending/ready/failed/
waiting/stale; text is exposed only while its analysis fingerprint remains
current. Narratives are not retained across restart and are never presented as
the authoritative price or scheduling decision.

## Owner Installation Verification (8 October 2026)

- Live tariff: `E-1R-AGILE-24-10-01-D`. The approved Ofgem benchmark now uses
  Merseyside and Northern Wales / direct debit (27.86 p/kWh).
- Exported the running old app's recent cache without modifying the original.
  Its 4,320 recent prices did not match the exact live tariff's official API;
  half-hour timestamp shifts did not explain the mismatch. That cache was not
  imported or relabelled, and the old app remains installed/running.
- With explicit approval, fetched 90 complete official tariff days (10 July
  through 7 October). Preview found no conflicts; imported all 4,320 prices
  without replacing live history. Export read-back and independent on-disk
  checks matched every price and all 90 imported provenance records.
- Schema-2 history contains 91 days including today. The original schema-1
  rollback store remains intact. Historical baseline coverage is ready (14 days).
- Learning totals remain dishwasher 113, washing machine 189, robot vacuum 46;
  Quick45 remains 22 and MixedLoad remains 3 / 51% confidence. Runtime and
  appliance costing are ready, with no integration errors or retired dashboard
  references in the post-upgrade audit.
- The owner approved `ai_task.openai_ai_task_2` for one manual provider test.
  The action correctly returned `waiting` without calling the provider because
  both HA and the official tariff API contain only 46 next-day periods.
  Actual provider generation is still pending complete next-day data.
- Post-import restart and live downgrade/re-upgrade verification passed.
  Temporarily installed v1.6.0-beta.3: runtime and appliance costing were ready,
  learning counts were unchanged and the old schema-1 store remained readable.
  Independent disk inspection confirmed that all imported prices and their
  provenance stayed intact in the separate schema-2 store during rollback.
  Restored v1.7.0-beta.1 and restarted: all 91 stored days, the corrected
  benchmark and unchanged learning counts returned without storage errors.
  Optional AI status reset to disabled as designed. One-to-four-hour cheapest
  windows matched independently calculated prices and start times; dashboard
  references and integration logs were clean. Stable remains v1.5.0.

## Follow-Up Verification (9 October 2026)

The physical MixedLoad wash completed normally: dishwasher learning is now 114
total, MixedLoad 4 runs at 61%; washing machine / vacuum remain 189 / 46.
Installed v1.7.0-beta.4 with stable EV editing and registered-hub compatibility
after fresh idle/no-queue/no-capture checks. One restart preserved all 222
entity/device identities, the exact dashboard configuration and 91 schema-2
history days. All appliance forecasts are ready and integration logs are clean.
The real EV form opens with retained defaults; production settings were not saved.
259 combined unit tests and minimum-HA lifecycle/device-registration checks pass.
The latest read-only audit still has no tomorrow prices and only 46 slots today;
AI stays disabled until a complete next-day snapshot is available. Independent
one-to-four-hour cheapest windows continue matching live tariff arithmetic.

## Current Acceptance (14 October 2026)

The combined beta.7 is installed and its branch is `beta/next`. A fresh evening
read-back and local replay match the live saved overnight request. Published
one-to-four-hour generic tariff windows also match independent arithmetic;
they intentionally differ from a programme's profile-weighted cheapest start.
No appliance command, settings change, restart or history import was made.

All 46 published next-day periods match Octopus's exact-tariff public API. The
final 23:00-midnight local hour is absent upstream as well as in HA. That is
enough coverage for the operational overnight schedule and cycle tails, not a
complete local day. Installed beta.7 kept classification and optional narrative
waiting/disabled under its existing calendar-day rule. The approved single
actual-provider test remained pending and no provider call was attempted.

The 15 October audit subsequently verified actual beta.7 wash completion and
learning. Genuine live price-revision observation remains a separate gate.
Merge and stable release are held until
the owner's 15 October review; documentation cleanup does not change the
installed release tag or HACS publication.

## Publication Policy Clarification (15 October 2026)

The owner confirmed that the approximately 16:00 publication normally supplies
most of tomorrow, with the trailing hour supplied later. Waiting for a complete
next calendar day is therefore not the intended operational readiness rule.
Implemented on `beta/next`: coverage-aware deterministic analysis, like-for-like historical
comparisons and explicitly scoped manual narrative eligibility as specified in
[the coverage plan](forecast-coverage-plan.md), without filling unknown prices.
The actual provider test follows tested and separately approved deployment of
that change. All 418 unit tests and the new minimum-HA synthetic-provider
acceptance pass, including revisions during an in-flight request. Automatic AI
remains disabled. This branch work changes no live configuration or release;
an external provider has not been tested with the new behavior.
