# Tariff Analysis (v1.6 Beta)

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
or incomplete tomorrow rates produce `waiting`. Percentiles use the midrank
for ties: <=25 is cheap, >=75 expensive, otherwise typical. Volatility is low
up to 5 p/kWh standard deviation, moderate up to 10, otherwise high. A strong
evening peak has a 16:00-19:00 mean above the day mean plus one standard deviation.
Shape similarity is centered correlation against the matching-wall-time median;
below 0.5 is unusual. Repeated autumn wall times are averaged per historical day.

The analysis-status attributes contain bounded statistics and at most one
local-day median curve, not the retained history database. History counts,
date range, schema and storage health are included in diagnostics. A corrupt
or unsupported store is preserved without overwrite and reported as limited.

Historical cap rebasing, import and optional AI narrative are not part of this
beta. No OpenAI API key is needed. The previous stable integration ignores this
new separate store on rollback; it does not delete it.

`load_optimizer.analyse_tariffs` accepts `entry_id` for manual re-analysis.
`load_optimizer.export_tariff_history` returns portable JSON via a service
response, using `entry_id` and optional `retention_days` (default 90, max 365).
The export declares schema, timezone and p/kWh units, and excludes unfinished
current/future days. It refuses export when storage is unhealthy.
