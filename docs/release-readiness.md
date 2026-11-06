# Release readiness

This is the acceptance record to complete before publishing the development
milestones. It is not permission to deploy, restart HA, operate hardware or
publish a release. No new release version has been assigned in this checkout.

## Evidence boundary (6 November 2026)

| Gate | Current evidence |
| --- | --- |
| Development implementation | Overnight scheduling, total-cost decisions, explanations, EV modes and optional metered switch control are implemented locally. |
| Synthetic acceptance | Run the complete validation runner and keep its generated source identity and results. Historic counts alone are insufficient. |
| Household source review | Read-only review identified suitable cable and charger-meter entities, a current-price-only EV tariff selection and unavailable charger hardware. No live settings were corrected. |
| Freshness and energy assumptions | Pending live verification of reporting cadence, usable capacity, wall power and efficiency assumptions. |
| Supervised physical acceptance | Pending for this development implementation; mocked service dispatch is insufficient. |
| Unfamiliar-user onboarding and desktop/mobile layout | Pending. Executable examples cover syntax and synthetic behaviour only. |
| GitHub checks | All six jobs passed for development commit `3e75912` in [run 42194714493](https://github.com/stevesherry123/load-optimizer-home-assistant/actions/runs/42194714493). New changes require their own run. |
| Promotion, versioning and publication | Pending; development is published to draft PR #26, with no merge, tag or release. |

## Immediate path to a feature release

1. Select the first feature scope. Dishwasher scheduling/costs is the proposed
   first delivery; advisory EV planning and automatic charging have separate
   acceptance needs. The current draft PR bundles the implementations, so any
   narrower candidate needs an explicit source selection and fresh validation.
2. Resolve the EV prototype overlap described below for any installation moving
   from that prototype. Do not assume a branch switch is a supported migration.
3. Verify live sources and assumptions; complete the physical acceptance relevant
   to the selected scope and the household/dashboard walkthrough.
4. Demonstrate fresh installation and backup/rollback, then prepare the exact
   release candidate, matching versions and notes. Re-run its required checks.
5. Review promotion and publication as a separate action. A green development
   branch is suitable evidence for proceeding to acceptance, not a stable release.

### EV prototype reconciliation blocker

The reviewed prototype tip is `70dafaffb09a2aeb07d20f27d42824c754f2f4ff`
(`feature/ev-charger-control`); the milestone implementation tip is `3e75912`.
Both use storage version 1 and key `load_optimizer.ev_control.<entry_id>`.
The prototype stores ownership as `owned_target`; the milestone session stores
`owned` and command lifecycle fields. The records are not interchangeable.
Although restored milestone records block commands pending reconciliation, that
alone does not establish a supported migration or preserve the identity of a
prototype-owned switch. A different configured switch makes that distinction
material. Neither branch should overwrite the other's journal without a reviewed
migration and recovery policy.

Before a combined EV release, define migration of old ownership and pending
commands, preserve the original physical target, and test matching/mismatched
switches, reload and rollback. Review prototype guided setup, delivery monitoring
and session energy/duration limits for intentional retention or exclusion.
Do not merge the two controller classes wholesale. The prototype and shared
beta refs were refreshed during this review; neither was modified.

A read-only live-source check on 6 November could not reach the HA endpoints.
The earlier unavailable charger readings remain historical; current hardware and
reporting freshness are unverified. No settings or device commands were changed.

## Evidence for the candidate

1. Finish edits and commit the candidate. Run the full
   [validation workflow](validation.md) from that clean commit. Include unit,
   security and all standard Home Assistant checks; selected suites are not
   evidence that unselected checks passed.
2. Retain results.json and summary.md. The source section must show an available
   revision, a clean working tree and matching before/after identity. It records
   a content fingerprint as well as the Git commit. Changing source during checks
   invalidates the result even when individual checks passed. Dirty-tree runs are
   useful during development but are not evidence for an unchanged release commit.
3. Run the required GitHub credential scan, HACS and hassfest checks, including
   the prospective merge where applicable. Local Bandit does not replace those
   checks. See [release channels](release-channels.md) for the actual triggers.
4. Complete [installation acceptance](installation-checklist.md) on a separate
   installation. Record actual versions, source behaviour and outcomes without
   public credentials or household identifiers. Test relevant restart and recovery
   paths. Preserve backup and rollback evidence.
5. Resolve or explicitly hold the release for every missing physical or user
   acceptance gate. Do not infer support for another charger or appliance model
   from this installation's success.
6. Prepare the final changelog and release-specific README; assign matching
   manifest/runtime versions only when the release scope is decided. Updating
   main documentation does not update existing published tags.
7. Review the exact candidate and the evidence before the separate promotion,
   installation or publication action. A prerelease and a full stable release
   reach different users; a branch name alone does not determine that audience.

Generated validation reports contain revision metadata and hashes, not source
contents or access tokens. Per-check logs and screenshots can still contain
installation data; review them before sharing. Do not commit generated reports,
private backups or live credentials to the repository.
