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
| GitHub checks | All six jobs passed for development commit `8e6e00e` in [run 41866813346](https://github.com/stevesherry123/load-optimizer-home-assistant/actions/runs/41866813346). New changes require their own run. |
| Promotion, versioning and publication | Pending; development is published to draft PR #26, with no merge, tag or release. |

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
