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
- [ ] Full unit, security and isolated HA checks from the clean candidate.
      Development-tree checks passed in both pinned environments; clean-commit
      confirmation is recorded separately in generated validation reports.
- [ ] GitHub credential, HACS, hassfest and both full pinned HA suites.
- [ ] Supervised dishwasher run: starts within the window, confirms once and
      records completion; cancellation and restart do not duplicate a request.
- [ ] Verify installed tariffs, programme eligibility and household cost inputs.
- [ ] Desktop/mobile inspection and unfamiliar-user scheduling walkthrough.
- [ ] Fresh-install, backup and rollback acceptance.
- [ ] Final version, matching manifest/runtime metadata and release notes.
- [ ] Review exact green candidate, then separately promote and publish.

Missing prices must notify and retain permission only inside the original window.
A late-finishing fallback must still start within it. Extra runs must have
positive total benefit and cannot displace a requested normal wash.

See [validation](validation.md) and [dishwasher setup](dishwasher-control.md).
Automated fixtures use synthetic sources and mocked commands; passing them does
not establish physical acceptance. No live deployment or release is authorised
by this record.
