# History Import And Optional Narrative (Development Only)

Branch: `beta/tariff-import-narrative-v1.7`. This is not part of stable v1.5.0
or the installed v1.6 analysis beta. No user history has been imported and no
live AI provider has been called as part of developing this branch.

## Portable Import

Use a JSON export from `load_optimizer.export_tariff_history`. The format is:

```json
{
  "schema": 1,
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
No external source download or redistribution rights are assumed.

## Optional Narrative

`load_optimizer.generate_tariff_summary` accepts `entry_id` and an explicit
`ai_task_entity`. It uses Home Assistant's `ai_task.generate_data` action:
https://www.home-assistant.io/actions/ai_task.generate_data/

AI is disabled by default and never called by the coordinator or a timer.
An explicit service call may incur costs through the selected provider.
No API key is configured in Load Optimizer. AI Task availability is checked at
runtime, so older Home Assistant versions without it retain deterministic
analysis without optional narrative.

Only an allowlisted compact analysis is sent, without entity IDs, credentials,
raw history or storage metadata. Incomplete next-day analysis cannot generate
a narrative. Provider failures, malformed responses and a 60-second timeout
are independent of scheduling and learning. Concurrent duplicate requests do
not cause concurrent provider calls. Status is disabled/pending/ready/failed/
waiting/stale; text is exposed only while its analysis fingerprint remains
current. Narratives are not retained across restart and are never presented as
the authoritative price or scheduling decision.

An actual historical export and the owner's preferred AI Task entity still
need confirmation before migration/provider testing. These operations have
not been enabled automatically on the live installation.
