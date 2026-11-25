# Branch consolidation — 25 November 2026

The consolidation candidate is `fix/dishwasher-deadline-recovery` (PR #33), now
reconciled with main at `661e28a`. Version `1.7.0-beta.13` identifies the combined
source; it is not a published release. Published beta.12 remains immutable and
installed on the owner system. No Home Assistant restart or installation is part
of this repository consolidation.

## Included work and closure criteria

| PR | Disposition when the combined candidate reaches main |
| --- | --- |
| #33 | Merge the deadline repair, preserved tariff quotes, delivery guard and build attribution. |
| #31 | Included by merge ancestry: retain onboarding, ownership and worker acceptance on minimum HA and pinned 2026.11.1. |
| #32 | Included by merge ancestry: retain published-tag auditing and release-archive fingerprints alongside global version progression. |
| #27 | Fully contained: dishwasher scheduling/cost candidate is superseded by the combined candidate. |
| #18 | Fully contained: shared beta history is included. Optional tariff analysis remains experimental; merging source is not stable feature acceptance. |
| #28 | Superseded as a dishwasher release route. Preserve its EV owner-trial branch and data/migration requirements; do not call EV control complete. |
| #26 | Keep open for unique EV controller/planning work; dishwasher milestones are covered by #33. |

Do not delete branches containing unique EV commits or active worktrees. Closing
an obsolete PR does not authorize discarding its unique work. Existing release
tags, learning data, settings, entity identities and trial evidence are retained.

## Reconciliation decisions

- Keep main's programme-selection error handling and readback check before Start.
- Keep main's explicit allowlists on general status sensor attributes.
- Keep the stronger beta disk-reservation check comparing the complete saved
  execution snapshot, including build version. Remove the duplicate attempt-only helper.
- Preserve bounded normal-wash permission, pinned applicable deadlines and
  recovery only before appliance commands. No change to the agreed late-finish fallback.
- Combine PR #32's exact-commit workflow-event checks and published-tag inspection
  with the beta stream's monotonic version checks. Audit of an existing release
  does not require it to be newer than itself.
- Keep the unified acceptance runner from shared beta and run every isolated HA
  check on both pinned environments, rather than reverting to a smaller subset.

## Acceptance and remaining tasks

The beta.12 automatic Eco50 cycle on 25 November recorded build_version beta.12,
a 02:00 attempt, confirmed operation and 06:25 completion. The stale 19 November
helper remained unchanged. One learning increment was observed. This validates
the installed repair, not the uninstalled combined candidate.

Before merging, require the combined commit's unit, security, HACS, hassfest and
both HA acceptance jobs to pass. Programme mismatch and selection-service error
must each prevent all Start commands. Status tests must reject accidental future
coordinator fields. Preserve cancellation, disk-reservation, restart and deadline
regressions.

Still open: power/duration estimation with chronological holdout validation,
actual-versus-estimated costs, transient overnight coverage diagnosis, EV advisory
commissioning and EV controller migration/hardware acceptance. These are not
closed by consolidating branches. Stable release and installation of the combined
candidate require their own versioned release and deployment checks.
