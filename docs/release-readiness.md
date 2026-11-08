# Dishwasher feature release candidate

The selected first feature release covers bounded overnight wash requests,
configurable window controls, normal-wash priority, strictly positive total-benefit
extra runs, configured operating costs and readable household controls.

This branch starts at `4606832`, the last dishwasher-only milestone commit.
Later EV planning and automatic charging changes are outside its scope. Existing
base advisory behaviour is retained. The broader draft PR #26 is not this release
candidate and must not be merged wholesale to deliver this scope.

## Acceptance record

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
- [ ] Fresh-install, backup and rollback acceptance.
      Isolated real-file scheduling restoration now has a dedicated acceptance
      fixture; full HA backup, learned-profile and older-release rollback remain pending.
- [ ] Final version, matching manifest/runtime metadata and release notes.
- [ ] Review exact green candidate, then separately promote and publish.

Missing prices must notify and retain permission only inside the original window.
A late-finishing fallback must still start within it. Extra runs must have
positive total benefit and cannot displace a requested normal wash.

See [validation](validation.md) and [dishwasher setup](dishwasher-control.md).
Use the [acceptance walkthrough](dishwasher-acceptance.md) to collect the remaining
installation, household-interface, physical and recovery evidence.
Automated fixtures use synthetic sources and mocked commands; passing them does
not establish physical acceptance. No live deployment or release is authorised
by this record.
