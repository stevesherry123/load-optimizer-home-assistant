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
