# Tariff Intelligence Development Plan

## Purpose

This plan brings the useful ideas from Octopus Intelligence into Load Optimizer
without reintroducing a second runtime or making the integration depend on one
energy supplier. v1.5.0 is now the stable publication
baseline. Analysis development takes place on `beta/tariff-analysis-v1.6`, is released
as a prerelease, and reaches `main` only after the acceptance checks below pass.

The accompanying detailed project brief remains the product specification. This
document records the implementation sequence and release gates derived from a
review of both repositories and the live Home Assistant installation.

## Current Delivery Status (8 October 2026)

Completed and live-verified through v1.5.0-beta.6:

- Regional Ofgem lookup, daily caching, effective dates and freshness diagnostics.
- Region configurable; owner now uses live tariff region D / direct debit
  (Merseyside and Northern Wales), after the approved 8 October correction.
- Native benchmark sensor and visible horizontal benchmark line.
- Main tariff chart: today only (24 hours), or today and tomorrow (48 hours)
  when next-day data exists. This supersedes the rolling-chart proposal below.
- Tariff-time rendering and a vertical Now marker refreshed every minute.
- Automation Capabilities retained at the bottom of the Dishwasher page.
- Lab dashboard retired; no further Lab functionality is requested.
- 162 tests passing; live learning counts unchanged by the dashboard updates.

Delivery order now approved by the owner:

1. Completed: v1.5.0 passed validation, merged to main and published as stable.
2. Implement live tariff history and deterministic analysis on a separate beta
   branch for v1.6.0, test missing-data recovery, DST, revisions, retention,
   restart persistence and independence from appliance learning.
3. After that implementation is validated, create a separate non-production
   branch for historical import and optional narrative summaries. Import defaults
   to dry-run and must never silently overwrite live history. AI remains optional.
4. HACS default-catalogue submission remains separate and unconfirmed.

The v1.6 implementation includes immutable slot/day models, fingerprints,
source-shared storage, complete-day capture, 365-day retention, matching-local
half-hour medians, 14-day warm-up, percentile classification, volatility,
evening-peak and centered shape analysis, and future-only one-to-four-hour
continuous windows. New entities are independent of appliance entities.
Cap-adjusted historical baselines remain a separate Stage 5 follow-up: raw
history and raw comparison are never silently described as cap-adjusted.

Release gate for v1.6: beta deployment/restart and preservation checks, followed
by observation across next-day publication and appliance cycles. Historical
comparisons need 14 complete recent days, either captured or explicitly imported.

Initial v1.6 live checks: learning counts 113 / 189 / 46 retained; current-day
history captured; incomplete 46-slot next-day feed correctly reported as limited;
all one-to-four-hour windows matched independent arithmetic from live rates.
Rollback to v1.5.0 and upgrade to v1.6.0-beta.3 succeeded with the same learning
counts, a healthy retained tariff store and matching window calculations.
Historical warm-up is now satisfied by the separately approved official backfill.
Longer publication/appliance-cycle observation remains pending before promotion.

Implemented next-branch design defaults:

- Portable JSON import with explicit schema, timezone and p/kWh unit metadata.
- Default 90 completed days, dry-run first, all-or-nothing validation and an
  explicit override before replacing any live-captured day.
- No silent external history download or assumed redistribution rights.
- Optional Home Assistant AI Task narrative, explicit/manual requests only,
  disabled by default, compact deterministic input and independently tracked
  pending/ready/failed/stale status. No raw history or credentials sent to AI.

Implemented on `beta/tariff-import-narrative-v1.7`: portable import, provenance
protection, atomic validation, independent narrative lifecycle and privacy/failure
tests. It is installed as v1.7.0-beta.1 for controlled owner testing, but is not
merged into main. The verified legacy adapter and service path have 212 combined
tests; all branch checks pass. The old cache was exported and preserved because
all 4,320 recent prices differed from the exact live tariff's official API.
With separate approval, 90 complete official days were imported instead.
All prices/provenance matched read-back and independent disk checks. Storage
contains 91 days including today and the 14-day baseline is ready. Learning
totals stayed 113 / 189 / 46 across import, restart and actual downgrade/re-upgrade.
Generic one-to-four-hour windows matched independent arithmetic, with clean
integration logs and dashboard references. The approved OpenAI AI Task action
returned waiting without a provider call because tomorrow has only 46 periods.
Actual provider testing and longer observation remain beta promotion gates.

The independent v1.5.1 publication preparation adds truthful installation and
dashboard guidance, corrects minimum HA to 2024.12, adds minimum-version import
CI and guards the shared learned-appliance store against a second hub. HACS
default-catalogue submission is planned for 9 October, not already completed.
EV options editing is the next separate development slice; cap-adjusted history
and the beta analysis dashboard remain subsequent work.

Longer observation is a release gate for new analysis, not a claim that can be
established by a short test run. Do not advertise history-dependent outputs as
ready before their warm-up requirement is met. Routine dashboard edits do not
require backups; use them for actual migrations or risky deployment changes.

## Review Findings

The Octopus Intelligence application contains several ideas worth retaining:

- deterministic analysis before optional AI commentary
- exclusion of elapsed or already-started slots from actionable recommendations
- one-, two-, and three-hour continuous cheapest-window calculations
- matching local half-hour prices against recent history
- explicit forecast completeness and baseline coverage diagnostics
- detection of unusual morning and evening peak shapes
- immediate recalculation when next-day rates arrive, with a timed fallback
- concise announcements generated without AI

The following implementation details should not be carried across unchanged:

- a second Home Assistant app/add-on runtime and scheduler
- a provider-specific `ai_feed` requirement
- direct publication of an unregistered sensor through the REST API
- an external history download as the primary operational datastore
- direct OpenAI API credentials held by this integration
- large forecast arrays on recorder-backed entity attributes
- duplicated source trees and manually installed dashboard JavaScript

Load Optimizer already has the stronger foundation: a provider-neutral tariff
parser, Home Assistant config entries, registered entities, integration-owned
storage, diagnostics, profile-weighted appliance costing, and native refresh
coordination. Tariff Intelligence should be a shared integration service beside
load-specific optimization, not a separate load entry or compatibility runtime.

## Architecture

### Shared tariff service

Add one integration-owned tariff service for each distinct normalized tariff
source. Learned-appliance and EV entries using the same source should reuse that
service and its history rather than each storing the same day.

The service owns:

- normalized `TariffSlot` and `TariffDay` models
- validation, completeness, provenance, and deterministic fingerprints
- a versioned Home Assistant `Store` independent of appliance learning data
- retention of 365 completed local days by default
- current and future outlook construction
- deterministic daily analysis and compact chart data

The existing tariff parser remains the only provider-format boundary. Analysis
code accepts normalized slots and must not refer to Octopus entity IDs.

### Persistence rules

- Store complete source days, including slots that have elapsed.
- Use future-only slots for recommendations and the rolling outlook.
- Never assume 48 slots; derive local-day boundaries and slot counts.
- Replace a stored day when its fingerprint changes and retain provenance.
- Prefer live Home Assistant data over imported data for the same day.
- Keep raw observed prices immutable; all cap-adjusted values are derived.
- Do not use Recorder history as an algorithmic dependency.

### Analysis boundary

Generic tariff analysis and load-specific optimization remain separate:

- Tariff Intelligence answers whether a day is cheap, typical, volatile, or
  unusual and identifies generic continuous low-price windows.
- Load Optimizer answers when a particular learned profile or EV should run.

The two may share normalized slots and history, but a generic two-hour window
must not replace profile-weighted appliance costing.

### Ofgem price-cap reference

Add an effective-dated electricity price-cap reference provider. Its default
automatic source should be Ofgem's regional unit-rate tables, refreshed at
startup and no more than once per local day. Although the lookup runs daily, the
underlying value normally changes quarterly.

The configured reference must include:

- electricity region
- payment method
- single-rate tariff type
- effective start and end dates
- unit rate in pence per kWh
- source URL, retrieval time, and parser version

The chart should label this as the `Ofgem default-tariff benchmark`, not as a
limit on the configured dynamic tariff. The price cap applies to default
tariffs, and Agile prices should not be described as capped at this line.

The outlook dataset should carry an effective-dated step series. It will appear
as a horizontal line on ordinary days but can change at the correct midnight if
the displayed horizon crosses a cap-period boundary.

Source precedence and failure handling:

1. A user-selected Home Assistant price-cap entity, when configured.
2. The validated official Ofgem table lookup.
3. A manually configured effective-dated reference.
4. The last known good value, marked stale with its retrieval time.

Never publish zero or silently substitute a national average after a failed
regional lookup. Validate the expected region, payment method, period dates,
units, and a plausible numeric range before replacing cached data. Keep
third-party APIs optional because they may require keys, change terms, or have
incomplete historical coverage.

### Home Assistant surface

Create a Tariff Intelligence device with a deliberately small entity set:

- analysis status
- tomorrow classification and average price
- raw and adjusted comparison with recent history
- pattern and volatility classifications
- evening-peak classification
- cheapest one-, two-, three-, and four-hour window sensors
- data-quality status
- deterministic summary
- optional AI summary and its independent status

Keep detailed statistics and the bounded outlook on attributes of dedicated
diagnostic/chart entities. Never expose the retained historical database as
entity attributes.

## Delivery Stages

### Stage 0 Repository and live baseline

- Preserve v1.4.4 on `main` until v1.5.0 validation completes.
- Retire the restored `Load Optimizer Lab` dashboard after preserving its
  `Automation Capabilities` card as a backlog item for the supported dashboard.
- Record current learning counts, tariff horizon, entity IDs, diagnostics, and
  production dashboard behavior before installing a beta.
- Treat the short post-restart tariff-source delay as `waiting`, not an error;
  refresh automatically when the source entities repopulate.

Gate: current tests pass and the live integration returns to `ready` with its
existing 94-period tariff horizon after restart.

### Stage 1 Canonical models and validation

- Add immutable tariff slot/day models and conversion from existing parser output.
- Add validation for gaps, duplicates, overlaps, invalid prices, and durations.
- Add DST tests for 23-hour and 25-hour local days.
- Add stable fingerprints over ordered timestamps, prices, source, and local date.

Gate: pure unit tests pass without Home Assistant and existing optimizer tests
remain unchanged.

### Stage 2 History store and live capture

- Add a versioned, integration-owned tariff history store.
- Capture complete current/next-day datasets after normalization.
- Deduplicate unchanged publications and replace revised days atomically.
- Prune to the configured retention period.
- Include store schema, counts, date range, and latest capture in diagnostics.

Gate: restart, rollback, duplicate-publication, revised-publication, corruption,
and migration tests pass. Appliance learning storage remains byte-for-byte
independent.

### Stage 3 Backfill and import

- Add `load_optimizer.import_tariff_history` with dry-run support.
- Validate schema and units before writing anything.
- Import the most recent 90 days by default and report imported, skipped,
  replaced, and rejected rows.
- Require explicit overwrite for replacing a live-captured day.

Gate: import is idempotent, malformed rows cannot damage the existing store,
and a backup/restore round trip reproduces the same fingerprints.

### Stage 4 Deterministic tariff analysis

- Calculate mean, median, min, max, range, standard deviation, and thresholds.
- Calculate deterministic cheapest continuous one- through four-hour windows.
- Build raw matching-half-hour baselines from completed historical days.
- Add recent-day percentile classification with an explicit warm-up state.
- Analyse household time bands and evening peak strength.
- Add centered shape similarity and relative volatility without an ML dependency.

Gate: synthetic tests cover vertical-shift invariance, anomalous curves, ties,
negative prices, incomplete days, DST, and 0/3/7/13/14-day warm-up states.

### Stage 5 Price-cap adjustment

- Add a versioned `PriceCapReference` model and additive rebasing.
- Preserve raw comparisons beside adjusted comparisons.
- Keep standing charges out of half-hour analysis.
- Make missing or out-of-range references visible rather than silently guessing.
- Add a daily cached Ofgem lookup with entity and manual fallbacks.
- Publish the current benchmark, effective period, source, freshness, and next
  scheduled refresh as native entity state and attributes.
- Add the benchmark step line to the outlook chart and tooltip.

Gate: a +3 p/kWh reference change moves only the monetary baseline by +3 p/kWh
and does not change shape similarity or raw history. Parser fixtures, stale-cache
behavior, regional selection, quarter-boundary charts, and upstream layout
changes are covered by tests.

### Stage 6 Native entities and events

- Add the Tariff Intelligence device and compact registered entities.
- Recalculate when relevant tariff entities change, with coordinator fallback.
- Publish `waiting`, `analysing`, `ready`, `limited`, and `error` distinctly.
- Add manual re-analysis and history-export services for diagnostics.

Gate: entity IDs remain stable across reload, restart, rollback, and upgrade;
missing next-day data never produces a definitive tomorrow classification.

### Stage 7 Dashboard consolidation

- Compare `Load Optimizer Lab` with the production dashboard card by card.
- Move useful controls, decision explanations, and boundary views into the
  integration dashboard or documented optional dashboard.
- Retain the approved 24/48-hour tariff-day chart using tariff-local time,
  not the browser timezone.
- Show forecast, historical median, optional percentile band, now marker, and
  cheapest two-hour window without fixing the axis at midnight or 48 points.
- Test desktop, mobile, UK, and a browser five time zones away.
- Retire the Lab dashboard only after its accepted ideas are present and the
  user has approved the production replacement.

Gate: both dashboards remain available during beta; no dashboard is deleted by
the integration; all referenced entities exist; travel-timezone rendering and
DST screenshots pass.

### Stage 8 Optional narrative

- Always publish a concise deterministic summary first.
- Prefer Home Assistant's AI Task integration for optional narrative generation.
- Send only the compact deterministic result, never raw history or credentials.
- Track disabled, pending, ready, failed, and stale summary states separately.

Gate: disabling or breaking AI has no effect on analysis, scheduling, entities,
or dashboards, and stale prose cannot masquerade as today's summary.

## Beta and Promotion Process

1. Implement in small commits on the appropriate `beta/**` branch.
2. Run unit tests, Home Assistant hassfest, HACS validation, and store migration
   tests on every pull request.
3. Publish the first installable build as a prerelease, provisionally
   `v1.5.0-beta.1`, without moving the stable HACS release.
4. Back up Home Assistant and the integration store before installation.
5. Install the beta only on the owner's instance and retain the previous stable for rollback.
6. Observe at least seven days, including next-day publication, a restart,
   missing-data recovery, a tariff revision, and at least one appliance cycle.
7. Compare deterministic outputs with an offline fixture and manual calculations.
8. Test beta-to-stable and beta-to-previous-stable rollback without learning-data loss.
9. Promote the validated commit to `main`, publish the corresponding stable version, and update the
   public documentation only after all gates pass.

## Decisions Needed Before Stage 3

1. Confirm the CSV file, exact columns, timezone convention, price unit, and
   redistribution terms. The existing Octopus Intelligence app uses Agile Buddy
   JSON, which should not become a silent production dependency.
2. Confirm the user's Ofgem electricity region and payment method. The public
   config flow should require both and should not infer them from an address.
3. Confirm whether one tariff source per Home Assistant installation is enough
   initially, or whether multiple regions/meters must be analysed independently.
4. Confirm that Home Assistant AI Task is the preferred optional narrative path;
   direct OpenAI API-key handling should not be ported from the old app.
5. Choose whether the first public chart may depend on ApexCharts Card or must be
   a bundled Load Optimizer frontend card. A bundled card is cleaner for users
   but materially increases the first release's review and testing surface.

## Publication Boundary

The tariff-intelligence work is not required to publish v1.5.0. Publication can
proceed while this branch develops, provided the public documentation describes
the current feature set accurately. Octopus Intelligence should remain available
as a reference until feature parity is demonstrated; it should then be archived,
not silently deleted, with a migration note pointing users to Load Optimizer.
