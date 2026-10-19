# Published Forecast Coverage Plan

## Decision And Scope (15 October 2026)

Released as `v1.7.0-beta.8` after separate owner approval and installed on
15 October. Live verification completed on 16 October; see
[deployment acceptance](forecast-coverage-acceptance.md). Stable promotion
remains separately reviewed. No external AI provider has been called for this change.

Acceptance on 15 October: 418 unit tests pass, including partial publication,
DST, matching historical intervals, invalid sources and stale narratives. A new
minimum-Home-Assistant smoke test verifies registered entities and the manual
service with a synthetic provider, including an in-flight price revision. No
external AI provider was called. Existing backend acceptance tests also pass;
the optional EV HTTP listener could not bind under the local sandbox.

The owner clarified that the normal approximately 16:00 publication contains
most, not necessarily all, of the next local calendar day. The trailing hour
arrives in a later publication. The 14 October observation of 46 contiguous
next-day periods ending at 23:00 Europe/London is therefore an expected operating
case, not a reason to block every analysis until midnight-to-midnight coverage.
Do not assume that publication always occurs at exactly 16:00 or infer a missing
price from this pattern.

Replace the single calendar-day readiness gate with separate checks for:

- a usable, validated published forecast;
- complete coverage of a particular scheduling candidate;
- a complete local day eligible for historical storage/import.

The installed beta.7 already checks the operational overnight window and cycle
tails independently. That scheduling protection must not be weakened.

## Coverage Contract

Derive coverage from normalized timestamped prices in the configured tariff
timezone, not browser time, a fixed slot count or an assumed 23:00 cutoff.

Retain `tomorrow_complete` as a truthful calendar-day fact. Add bounded coverage
metadata for the target date, actual start/end, known duration, expected local-day
duration, uncovered trailing interval, and whether an internal gap exists.
Distinguish missing next-day data, usable trailing-partial data, full-day data,
and invalid/gapped data. Never call a partial calendar day complete or claim
that a provider has published its entire market horizon without evidence.

Implemented readiness rule: a valid contiguous next-day prefix from
local midnight covering the existing overnight, morning, daytime and evening
bands (through 19:00 local) may be analysed as a usable published forecast.
The remaining late band may be partial. This admits the observed 23-hour feed
without accepting a lone slot or a short morning-only snapshot as a useful
next-day outlook. This is a semantic coverage threshold, not a provider
slot-count assumption. Shorter snapshots may expose covered-period statistics
but retain limited readiness for classification and optional AI.

An internal hole with later prices is not an expected unpublished tail. Keep
gap/conflict/overlap, invalid price/unit/timezone and source/storage error checks
explicit; never disguise them as ordinary publication coverage or bypass them
for AI. Existing actionable generic windows still require contiguous prices
through each window's end and exclude elapsed/already-started slots.

## Deterministic Analysis

- Calculate available-period statistics, volatility and covered time bands as
  soon as the readiness rule passes. Label them as the published portion of the
  target day, with actual coverage, not an unconditional full-day average.
- Compare each historical day over the same covered wall-time intervals and
  duration weights. Do not rank a 23-hour forecast against 24-hour historical
  means, which would bias cheap/typical/expensive classification.
- Keep the 14 recent completed-day baseline requirement. Exclude historical
  candidates that cannot supply the matching intervals and report warm-up or
  insufficient comparison coverage rather than guessing.
- Retain tariff-local, duration-aware DST handling and the existing documented
  treatment of repeated wall times. Do not compare the missing target tail with
  an unrelated historical hour or extrapolate a full-day total.
- Expose complete/partial/unavailable coverage for each time band. A covered
  evening peak can be reported; an incomplete late band must not look complete.
- Describe cheapest windows as cheapest within the known searchable horizon,
  not guaranteed cheapest across an unpublished remainder. Generic constant-load
  windows remain distinct from programme-profile scheduling.

Completed historical storage and portable import keep their strict full-local-
day validation. Partial forecasts are not padded, imported or saved as completed
historical days. No storage migration or change to appliance learning is needed.

## Optional AI And Refresh

Allow an explicitly requested AI summary when the deterministic published-
forecast analysis is usable, even if `tomorrow_complete` is false. AI input must
include the target date, timezone, actual coverage and partial-day scope. Extend
the existing compact allowlist and instructions, not the raw-history payload.
The summary must disclose the unavailable tail and must not invent its prices,
claim full-day negative-price absence or issue appliance commands.

AI stays manual-only, independently permission checked, disabled by default and
subject to the existing timeout, duplicate-request, failure and privacy guards.
The previously agreed one-provider test remains one manual attempt after the
new behavior is implemented, tested and separately installed; planning does not
make a provider call or authorize background generation.

Recalculate deterministically when source rates change, using the existing
coordinator refresh as fallback. Do not wait until the next 16:00 tick if rates
arrive earlier, and do not assume a timer proves publication completeness.
Coverage/date/price changes must change the narrative fingerprint and mark the
old text stale, including while a provider request is in flight. Do not request
another paid narrative automatically. Handle target-date rollover explicitly.

The existing approved 24/48-hour main chart layout remains unchanged. Any new
coverage labels must use tariff-local time and distinguish an unpublished tail
from a rendering error; do not change the graph's axis policy in this work.

## Implementation Sequence

1. Add pure coverage/readiness helpers beside `optimizer/intelligence.py`;
   preserve strict `complete(TariffDay)` and stored-day validation.
2. Update deterministic analysis, matched-period historical comparisons and
   bounded quality metadata in `tariff_intelligence.py`; retain entity IDs.
3. Update `narrative.py` readiness, compact input, coverage/date fingerprints
   and instructions. Do not change service permissions or automatic-call policy.
4. Update user-facing analysis documentation to describe installed behavior
   only after code acceptance. Keep this planning record distinct from delivery.
5. Run unit and actual minimum-HA acceptance before proposing a beta installation.
   Compare against the observed publication and existing offline arithmetic.
6. After separately approved deployment, perform the single manual provider
   test and observe a later publication/rollover. Review promotion separately;
   no change to the pending upstream HACS catalogue request.

## Acceptance Matrix

- Normal 46-slot trailing-partial publication: usable, explicitly partial,
  coverage-matched baseline; manual AI eligible, no background provider call.
- Full 48-slot ordinary day: same full-day numerical results as before.
- Full 46-slot spring and 50-slot autumn days: genuinely complete local days,
  not mistaken for the ordinary-day trailing-partial case.
- A short prefix, missing start, internal hole, conflicting duplicate, invalid
  unit/price/timezone, failed source or unhealthy storage: limited/error as
  appropriate; no misleading whole-day conclusion or AI bypass.
- Added tail or revised prices: refresh statistics, baseline and fingerprint;
  hide stale prose; unchanged refreshes cause no repeated writes/provider calls.
- Midnight/16:00 boundaries and a browser five timezones away: target dates,
  coverage and comparisons remain tariff-local and never include invented rates.
- A candidate crossing an unpublished tail or an internal gap remains blocked;
  candidates with complete operational coverage keep existing behavior.
- History/import/export, rollback, learning counts, entity identities, manual
  control and overnight/negative-price safety remain unchanged.

Release gates are normal-publication analysis and later revision/rollover
acceptance, not a requirement that every next-day feed already contain an entire
calendar day. Actual appliance execution/learning remains a separate live gate.
