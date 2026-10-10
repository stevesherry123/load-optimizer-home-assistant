# Contributing

Use GitHub Issues for bugs and small proposals. Include the integration release,
Home Assistant version, affected load type and steps to reproduce. Redact
credentials, addresses, device identifiers and private entity data.

`main` contains the stable product. Work in a separate branch and open a pull
request. Tariff analysis (`beta/tariff-analysis-v1.6`) and import/AI
(`beta/tariff-import-narrative-v1.7`) remain stacked development branches until
their release gates pass. Do not merge them just to prepare a HACS submission.

Run `python -m unittest discover -s tests`. CI must also pass HACS validation,
hassfest and the declared-minimum Home Assistant import smoke test without
ignored failures. The import smoke test is not a full fresh-install test.

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

Delete completed feature/fix branches after their changes are merged. Retain the
two stacked tariff beta branches while their separate promotion gates remain
open. Preserve unique superseded work with an explicit archive tag if retiring
its branch; an archive tag is not a GitHub release. The
[9 October cleanup record](docs/branch-cleanup-2026-10-09.md) records retained
branches and recoverable commits. Do not delete the HACS submission fork branch
while the upstream request is open.
