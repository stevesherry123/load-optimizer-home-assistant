# Clean-Install Acceptance

These checks use synthetic entities in a temporary HA configuration, no legacy
database, no real appliance, no AI provider and no supplier network calls. They
do not establish physical manufacturer acceptance or unfamiliar-user usability.

## Automated checks

Run the unit suite and the isolated onboarding test with the declared-minimum
Home Assistant and the repository's test dependencies installed:

```sh
python -m unittest discover -s tests
python tests/ha_onboarding_smoke.py
```

The tests exercise the documented generic and Home Connect examples, real config
flows/selectors, registered entities, storage, reload/restart and learning without
an import. Device calls are intercepted and the HTTP listener is mocked. Check
the current CI results rather than treating an old test count as current evidence.

Configuration regressions cover malformed input, duplicate identities/keys,
ambiguous permissions, source/unit warnings, cancelled edits and preserving
learning/registered identity. Settings changes must not silently interrupt a
known capture or queued request. See [runtime safety](runtime-safety.md).

## Human and physical acceptance

Before relying on a supported release, an unfamiliar tester should:

1. Follow its README/setup guide on a separate installation, not an unpublished
   checkout or a copy of the maintainer's production configuration.
2. Identify their own power, cumulative-energy and future-tariff inputs.
3. Complete an ordinary cycle, verify learning and distinguish a recommendation
   from a queued start.
4. Verify the starter dashboard has no missing entities and a HACS update does
   not overwrite their customised copy.
5. For supported Home Connect control, leave automatic modes off during an
   explicitly approved supervised manual cycle. Verify actual completion before
   separately enabling automatic modes. Retain every device safety interlock.
6. For EV planning, verify units, connection state and price coverage without
   assuming advisory signals operate a physical charger.
7. Find troubleshooting guidance and prepare a useful redacted issue report.

Human/physical acceptance, live deployment, publication and isolated tests are
separate evidence. Main documentation changes do not rewrite installed releases
or existing tags. See the [roadmap](roadmap.md) for planned improvements and
[release channels](release-channels.md) for distribution behaviour.
