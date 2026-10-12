# Clean-Install Acceptance

These checks are independent of the owner's migrated installation. They use
synthetic entities in a temporary HA configuration, no legacy database, no real
appliance, no AI provider and no supplier network calls. They do not claim a
physical manufacturer acceptance test or a visual browser test.

## Automated Checks

```sh
python -m unittest discover -s tests
```

`test_onboarding.py` reads the exact documented appliance lists, captures a
complete synthetic cycle and checks recommendation eligibility. It also covers
the old missing-policy failure, programme-name matching and local guide links.

With the declared-minimum Home Assistant and its test dependencies installed:

```sh
python tests/ha_onboarding_smoke.py
```

This separate test uses real config flows, selectors, registered entities,
storage and reloads. It verifies both appliance examples, the starter dashboard's
entities and customised storage-mode configuration across reload/restart, learning
without an import, off-by-default control, complete-reference activation without
an automatic request, persisted learning and identity, and the EV guide's
capacity/connection templates. All device-service calls are intercepted in the
test; HA's HTTP listener is mocked and no test login is created. CI runs it in
the minimum-HA job.

## Local Verification: 10 October 2026

On `docs/onboarding-clean-install`, against Home Assistant 2024.12.0:

- All 230 unit tests pass, including nine documentation-example/link regressions.
- Both fresh appliance paths pass learning, registration, dashboard persistence,
  reload/restart and off-by-default automatic-control checks.
- EV capacity and binary-connection adapters pass actual template integration
  checks; disconnected and unavailable inputs do not produce charge-now signals.
- Existing platform/config-flow import, dashboard-colour, EV lifecycle and
  security/permission acceptance checks pass. HTTP listeners are mocked for
the onboarding and EV lifecycle runs; no test login or real device is used.

These are local isolated results, not a live HA deployment, remote HACS/hassfest
result or an unfamiliar-user/physical release-gate sign-off.

## Human Release Gate

Before broad promotion, a tester unfamiliar with the owner's setup should:

1. Follow the README and setup guide on a separate HA installation, starting
   from the intended stable release, not an unpublished checkout.
2. Identify their power, cumulative energy and future tariff sources without
   borrowing the owner's meter or device IDs.
3. Complete one ordinary cycle, observe its count increment and find a priced
   recommendation. Explain why this is not a queued start.
4. Add the starter dashboard and confirm no missing entities or custom-card
   dependencies. Confirm a normal HACS update leaves their customised copy intact.
5. For a supported ID `1` Home Connect dishwasher only, configure and activate
   control while both automatic modes stay off. Perform an explicitly approved,
   supervised manual wash, verify actual completion and only then consider
   separately enabling each automatic mode.
6. For EV planning, verify units, connection behaviour, complete rate coverage
   and plan signals without assuming any charger-control automation exists.
7. Find the troubleshooting route and prepare a useful, redacted issue report.

An unpublished docs branch does not repair an existing release's versioned
README. Include the reviewed guides in an explicitly approved future release;
never rewrite old tags. HACS downloading, release-specific documentation and
live appliance acceptance remain distinct from these isolated tests.

## Still Separate Work

- Guided appliance editing and full tariff completeness/unit preview.
- Programme-policy UI and configurable native controller target.
- Installation-specific dashboard generation and desktop/mobile visual checks.
- Privacy-safe screenshots, issue forms and a small community onboarding trial.

None is implemented merely by documenting its current workaround.

## Configuration Validation Slice: 10 October 2026

Local development on `feature/onboarding-validation` adds executable parser and
validation regressions, plus real minimum-HA failed/cancelled/confirmed edits.
It covers malformed input, duplicate effective IDs, quoted false permissions,
source-unavailable/unit warnings, unchanged memory before confirmation, learning
and registered identity after saving, and continued off-by-default control.
The pre-save parser and runtime parser are shared. See
[the scoped plan and remaining gates](onboarding-development-plan.md).

The earlier 230-test result describes the documentation commit, not this later
runtime slice. Remote CI, browser/mobile inspection, representative migrated
configuration and unfamiliar-user acceptance are still separate promotion gates.

Final local results for the runtime slice: 248 unit tests; real minimum-HA
fresh setup, source review, cancellation, active-capture/queued-request save
guards, reload and persisted restart; EV lifecycle, platform imports, dashboard
templates and security smoke checks all pass. Bandit reports no findings with
no skipped checks. These results do not constitute live deployment or remote CI.

## Runtime Safety Review: 12 October 2026

On `fix/runtime-data-safety`, 276 unit tests pass. The real minimum-HA onboarding
checks also verify each learned-hub settings section defers both synthetic active
captures and queued starts, preserving options, requests, memory and registered
identities. Multi-source review checks each window entity independently. Both
documented appliance examples still pass setup, learning, save/reload and
persisted restart. The separate runtime-safety acceptance and remaining release
gates are recorded in [runtime safety repairs](runtime-safety-repairs.md).

The owner approved pushing this repair branch and opening a review request in
this repository. This does not approve a main merge, release, installation or
changes/comments on the HACS catalogue submission.

The subsequent approved planning-boundary follow-up adds nine unit regressions
(285 tests total) and range-filtering real-HA calendar acceptance. It covers late
no-run events, longer forecast tails, green overlap, active-capture padding and
startup model restoration. Learning and identities remain unchanged during
normal recommendation scans. See the repair record for the current scope;
release, production installation and physical acceptance remain separate.
