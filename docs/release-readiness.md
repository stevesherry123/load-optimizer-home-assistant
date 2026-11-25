# 1.7.0 public release record

Development is consolidated on `main`. The public feature scope is dependable
dishwasher scheduling, configured operating costs and readable controls, alongside
existing appliance learning, EV advisory plans and Ofgem comparison. The newer EV
planning/controller branch is excluded.

## Accepted behaviour

- One-wash permission has a fixed authorised start window. Prices may recover
  only within that window and before device commands begin.
- Prefer a complete overnight fit. When none fits, choose the cheapest eligible
  start inside the window, even when completion is later. A configured applicable
  travel deadline remains a hard constraint. No new hard overnight-finish opt-in
  is introduced. Existing explicit windows and control opt-ins are preserved.
- Extra runs require strictly positive net benefit per run, including configured
  costs. A requested normal wash need not be profitable.
- Programme selection is confirmed before Start. Persisted command reservations,
  fresh physical/source checks, cancellation, shutdown and uncertain-start holds
  prevent unsafe redispatch.

## Evidence

- Consolidation PR #33 merged main, #31 compatibility and #32 release-package
  verification, preserving the shared beta/dishwasher histories. Its exact source
  and prospective merge passed all six GitHub jobs; main `5dcd28e` also passed.
- 594 unit tests and 22 isolated HA acceptance scripts per pinned environment
  passed at the consolidation checkpoint. The stable metadata/preflight changes
  require their own final checks before publication.
- Installed beta.12 produced an automatic Eco50 cycle on 25 November: its saved
  snapshot identified beta.12, the wash started around 02:00, confirmed operation,
  finished around 06:25 and incremented learning once. The unchanged stale travel
  deadline did not block the newly authorised request.
- Installation evidence includes a protected owner configuration/database backup,
  exact source-file comparison, preserved registered identities, completed learning
  and control values, plus Marketplace channel/default-target refresh checks.
- Isolated upgrade/rollback, disk persistence, outage recovery, cancellation and
  restart acceptance use synthetic data and forbid real appliance commands.
  They do not claim a full household backup has been restored on live hardware.
- Dashboard templates have desktop/mobile and rendering acceptance. An unfamiliar
  user's walkthrough remains useful follow-up; it has not been claimed complete.

## Public limitations and follow-up

Learned duration and energy are estimates. Recent cycles exceeded forecasts;
recalibration, higher-resolution profiles and chronological holdout validation
remain open. Forecast electricity prices are not final billed costs. Only costs
configured by the user can be included; unconfigured consumables are disclosed.

A transient overnight tariff-coverage warning recovered before the accepted run;
its cause still needs diagnosis. Missing or invalid prices must continue to block
starting rather than imply zero cost.

Tariff history, analysis/import and manually requested AI summaries remain optional
experimental capabilities. They do not authorise appliance commands. New automatic
EV control and owner-trial journal migration remain excluded and unaccepted.

## Publication checks

From clean current main, run:

```
python dev/check_beta_release.py v1.7.0 RUN_ID --stable
```

The compatibility filename is retained, but `--stable` requires a stable version,
matching manifest/runtime/changelog, current remote main, an unused tag, forward
release ordering and all six successful jobs on the exact commit. Publish that
commit as a full GitHub release marked latest; never move existing tags. Verify
again with `--stable --published`, then compare the downloaded source package's
fingerprint with the validated Git tree. Publication does not install or restart
Home Assistant; any owner upgrade is a separate deployment.
