# Forecast Coverage Acceptance

## Deployment Verified 16 October 2026

Published `v1.7.0-beta.8` from `f5247b8bd91060ad86a0c17b6031604c92e0a918`
after 418 unit tests and all five GitHub validation jobs passed. The owner
approved continuing through beta deployment. HACS installed the selected version;
one restart loaded beta.8. The cloud endpoint temporarily returned 502 while
reconnecting and recovered without another restart.

The immediate before/after comparison verified:

- All 222 registered entity identities and seven device identities preserved.
- Both dashboard definitions unchanged.
- All 18 learning/profile/policy entities unchanged across restart.
- All 98 stored tariff-history days and source metadata preserved.
- Appliance controls and the queued overnight request unchanged.
- A real 23-hour next-day forecast analysed as usable but incomplete, with a
  one-hour missing tail explicitly disclosed and 14 matching comparison days.
- Optional AI remained disabled until explicitly requested.

The subsequent live overnight automatic wash completed and incremented total
and programme learning correctly. The morning queue was clear, beta.8 remained
loaded and the current integration log contained no errors. Target-date rollover
correctly returned to waiting when the next day's prices were absent. Private
household snapshots and detailed times are retained locally, not in this repository.

## Remaining Acceptance

- Perform the previously approved single manual external-provider test after
  fresh next-day prices make analysis usable. No provider call was attempted
  during the morning's missing-price state.
- Observe a live trailing-price arrival or price revision and stale-narrative
  behavior. Synthetic minimum-HA tests cover both, including in-flight revisions.
- Observe repeated free-price appliance execution before stable promotion.

Stable remains v1.5.7. This prerelease does not merge beta/next into main or
change the HACS catalogue submission.

## Provider Test 17 October 2026

One real call through the owner's configured Home Assistant AI Task completed
using an explicitly dated replay of genuine published tariff data. No live
source prices, control settings or production analysis were replaced. The live
next-day gate correctly remained closed because tomorrow's prices were absent.
Retained runtime analysis snapshots were not available from Recorder, so this
test does not establish retrospective live revision acceptance.

Provider connectivity passed, but output quality failed: the returned prose
contradicted the tariff-local coverage and confused historical baseline warm-up
with a price trend. Do not mark the external-provider quality gate passed.

An unreleased beta/next correction now prepends authoritative analysis facts
and requests only qualitative provider commentary. Responses repeating numerical
facts, coverage claims or warm-up wording fail closed with
`unverified_narrative_facts`; no prose is exposed. This guard reduces the observed
failure mode but is not proof that arbitrary AI commentary is factually correct.
The real malformed response is covered by a privacy-safe regression fixture.
All 421 unit tests pass. The correction is not installed in beta.8.

The real generated narrative became stale and hid its text after controlled
price-revision and tail-arrival replays, with exactly one provider call total.
These are controlled acceptance checks, not observed upstream revisions.
An end-to-end production-service generation and natural revision observation
remain pending. Another provider attempt requires a new explicit request;
the previously approved single call has been used.

Repeated real free-price execution is deferred at the owner's request until
suitable opportunities occur in the coming days.

### Additional Authorized Provider Test

After the owner's instruction to continue, one additional dated real-tariff
replay tested the corrected prose path. The integration rendered the date,
23-hour coverage and average from deterministic analysis correctly. Controlled
price and coverage revisions again hid the generated text without another call.

The provider still added an unsupported explanation about future energy demand.
Therefore the prose-quality gate remains open. A further unreleased correction
rejects speculative causal or forecasting wording as
`unsupported_narrative_inference` and requests only the supplied classifications.
The observed response is covered by another regression test; all 422 unit tests
pass. This conservative lexical guard can reject otherwise useful prose and
does not establish general factual correctness. Two real provider calls were
used across the two explicitly authorized attempts; no automatic retry occurred.

Do not publish or install another beta claiming successful AI quality acceptance
from these tests. Natural upstream revision observation and an end-to-end live
service generation remain distinct from replay. Keep AI opt-in and experimental;
further provider calls require approval. No additional beta was published or
installed during this retest.

### Constrained Finding Selection

The owner's subsequent instruction to implement the replacement authorizes
local tests, one real structured-provider attempt and a tested beta deployment.
The new beta/next path removes lexical prose filters and accepts only a bounded
list of IDs from a catalogue of deterministic findings. All displayed text is
rendered locally; unknown selections and extra response fields fail closed.
All 428 unit tests pass, including the original real prose failures, selection
bounds, mandatory coverage/warm-up notices, exact local-time rendering and
stale-result handling. Provider and deployment results are recorded separately
when completed; local success alone is not live acceptance.
