# Dishwasher feature release candidate

The selected first feature release covers bounded overnight wash requests,
configurable window controls, normal-wash priority, strictly positive total-benefit
extra runs, configured operating costs and readable household controls.

The reconciled candidate combines the dishwasher-only work with the
`v1.7.0-beta.11` programme estimates. Later EV planning and automatic charging
changes are outside its scope. Existing advisory behaviour is retained. The
broader draft PR #26 is not this candidate and must not be merged wholesale.

## Acceptance record

Before tagging a beta, run `python dev/check_beta_release.py vX.Y.Z-beta.N RUN_ID`
from the clean candidate checkout. It checks matching versions and release notes,
local/remote tag collisions and the six GitHub validation jobs on the exact SHA.
It does not create a tag, publish a release, verify live rollback or approve a
deployment.

- [x] First feature scope selected by the user: dishwasher scheduling and costs.
- [x] Separate source branch prepared without later EV implementation commits.
- [x] Clean implementation commit `473830b`: 536 unit tests, Bandit and all 20
      isolated HA checks passed in each pinned environment (2026.10.2/2026.10.4),
      with clean, unchanged source identities in generated validation reports.
- [x] All six GitHub jobs passed for `473830b`, including credential, HACS,
      hassfest and both full HA suites: [run 42195678559](https://github.com/stevesherry123/load-optimizer-home-assistant/actions/runs/42195678559).
      Later commits need their own checks before promotion.
- [ ] Supervised dishwasher run: starts within the window, confirms once and
      records completion; cancellation and restart do not duplicate a request.
- [ ] Verify installed tariffs, programme eligibility and household cost inputs.
- [x] Inspect the dishwasher cards in isolated HA at desktop and phone widths.
      See the [browser review](dishwasher-acceptance.md#browser-review-evidence).
- [ ] Unfamiliar-user scheduling walkthrough on the trial installation.
- [x] Isolated storage upgrade, restart and paired rollback from the published
      `v1.5.9` package, with synthetic learning and native-control settings and
      all device service calls forbidden. Repeat on the final release SHA.
- [ ] Fresh-install, whole-HA backup and supervised owner rollback acceptance.
      The isolated storage rehearsal is not evidence for a real backup restore.
- [ ] Confirm the finish target policy. The draft currently allows a clearly
      labelled late finish; a strict finish deadline is a different policy.
- [ ] Final version, matching manifest/runtime metadata and release notes.
- [ ] Review exact green candidate, then separately promote and publish.

Missing prices can retain permission only inside the original window and only
before device commands begin. A late-finishing fallback in the current draft
must still start inside that window. Extra runs must have positive total benefit
and cannot displace a requested normal wash.

See [validation](validation.md) and [dishwasher setup](dishwasher-control.md).
Use the [acceptance walkthrough](dishwasher-acceptance.md) to collect the remaining
installation, household-interface, physical and recovery evidence.
Automated fixtures use synthetic sources and mocked commands; passing them does
not establish physical acceptance. No live deployment or release is authorised
by this record.
