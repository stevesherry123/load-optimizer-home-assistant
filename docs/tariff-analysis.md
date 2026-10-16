# Tariff Analysis (Testing Channel)

This feature originated in v1.6 and is now part of the combined `beta/next`
branch, installed as v1.7.0-beta.8 for controlled testing. It is not part of
published stable v1.5.7. See [release channels](release-channels.md).

This page describes beta.8 coverage behavior, verified live on 16 October.
See the [coverage acceptance record](forecast-coverage-acceptance.md).
Completed historical storage/import remains strict.

Tariff Intelligence is read-only. It does not change appliance scheduling,
EV control, learned programs, or existing dashboard entity IDs.

The integration captures complete local tariff days into a separate Home
Assistant Store. Entries with the same configured tariff entities, timezone
and units share that history. Incomplete days are not persisted; changed source
days replace the previous version. Identical publications cause no extra write.
Retention is 365 completed days plus the current day and tomorrow.

The Tariff Intelligence device exposes analysis status, tomorrow average and
classification, volatility, evening peak, pattern, quality, a daily summary and
cheapest continuous one-, two-, three- and four-hour start timestamps. Window
attributes include average p/kWh and cost for a constant 1 kW load. These generic
windows do not replace profile-weighted appliance recommendations.

Already-started slots are excluded from actionable windows. Equal-cost windows
choose the earliest start. Gaps cannot be bridged. A complete local day can have
46, 48 or 50 half-hour slots depending on daylight saving.

Historical comparisons require all 14 recent completed local days. Until then
classification is `warming_up`, never a guessed cheap/expensive label. Missing
tomorrow rates or an internal gap produce `waiting`. A contiguous publication
from local midnight through at least 19:00 is usable with explicit partial-day
scope. Unknown trailing prices are excluded, never filled. Historical means
use the same covered wall-time intervals and target duration weights; historical
days missing a required interval cannot satisfy the 14-day baseline. Percentiles use the midrank
for ties: <=25 is cheap, >=75 expensive, otherwise typical. Volatility is low
up to 5 p/kWh standard deviation, moderate up to 10, otherwise high. A strong
evening peak has a 16:00-19:00 mean above the day mean plus one standard deviation.
Shape similarity is centered correlation against the matching-wall-time median;
below 0.5 is unusual. Repeated autumn wall times are averaged per historical day.

`tomorrow_complete` remains a strict calendar-day fact, while `forecast_usable`
also checks source and storage health. Forecast attributes expose target date,
timezone, known/expected duration, missing tail and per-band coverage. Tomorrow
summary sensors carry `analysis_scope` and `forecast_coverage`; their entity IDs
are unchanged. Generic windows are cheapest within the known searchable horizon.

The analysis-status attributes contain bounded statistics and at most one
local-day median curve, not the retained history database. History counts,
date range, schema and storage health are available on the local analysis
entity; downloaded diagnostics deliberately omit identifying metadata. A corrupt
or unsupported store is preserved without overwrite and reported as limited.

Historical cap rebasing remains unimplemented. The combined beta also contains
portable import and an optional manually requested AI narrative, documented in
[history import and narrative](history-import-and-narrative.md). Neither changes
the deterministic analysis. No OpenAI API key is held by Load Optimizer. Stable
rollback ignores the separate history store; it does not delete it.

`load_optimizer.analyse_tariffs` accepts `entry_id` for manual re-analysis.
`load_optimizer.export_tariff_history` returns portable JSON via a service
response, using `entry_id` and optional `retention_days` (default 90, max 365).
The export declares schema, timezone and p/kWh units, and excludes unfinished
current/future days. It refuses export when storage is unhealthy.
