# Contributing

Use GitHub Issues for bugs and small proposals. Include the integration release,
Home Assistant version, affected load type and steps to reproduce. Redact
credentials, addresses, device identifiers and private entity data.

`main` contains stable functionality and approved unreleased improvements;
the latest full GitHub release, not the branch tip, is the published stable
product. `beta/next` is the single combined testing branch for tariff analysis,
history import, optional AI and scheduling repairs. The old stacked tariff
branches are retired. Open a focused pull request for proposed changes; do not
promote beta work just to prepare a HACS submission or tidy the branch list.

Use the [version-checked validation environment](docs/validation.md) and run
`python dev/validate.py` before pushing changes. Local acceptance and GitHub use
the same declared HA/frontend and Python minor versions. Every independent HA
check runs, even if an earlier check fails; the overall result still fails.
The standalone unit suite also remains available through
`python -m unittest discover -s tests` with PyYAML installed. CI must additionally
pass HACS, hassfest and the security/credential scans without ignored failures.

For onboarding changes, also run `python tests/ha_onboarding_smoke.py` in the
minimum-HA environment. See [clean-install acceptance](docs/onboarding-acceptance.md)
for isolated coverage and the remaining human/physical release gates. Keep the
documented examples executable; do not base new-user acceptance on migrated data.

Keep changes scoped and preserve entity IDs, learning data and opt-ins. Test
reload/restart and upgrade/rollback for persistence changes; test desktop/mobile
and tariff-local time for chart changes. New physical control must be explicitly
enabled and must not bypass appliance safety checks.

Stable releases use matching manifest/runtime versions and a full GitHub
release created after successful checks. Development builds use prerelease
versions and GitHub's prerelease flag. Never move or replace a published tag.
Home Assistant installations do not run two channels of this same integration
domain side by side; use separate installations for isolated beta testing.

A push to `main` is not a stable release. Publish only from a validated exact
commit after incrementing matching versions and updating the changelog. Do not
publish an experimental branch as a full stable GitHub release: HACS follows
release status, not the branch's name. Public betas are isolated from normal
updates, not hidden from GitHub visitors. See [release channels](docs/release-channels.md).

Delete completed short-lived feature/fix branches after their changes are merged.
Retain `main` and `beta/next`; keep feature-specific acceptance gates in the
roadmap rather than creating a new permanent branch for each beta version.
Preserve unique superseded work with an explicit archive tag before retiring
its branch; an archive tag is not a GitHub release. The
[14 October cleanup record](docs/branch-cleanup-2026-10-14.md) records the earlier
consolidation and recoverable history. Experimental charger control remains on
`feature/ev-charger-control`; general repairs are selectively carried into the
shared beta without its physical-control code. Do not delete the separate HACS
submission fork branch while the upstream request is open.
