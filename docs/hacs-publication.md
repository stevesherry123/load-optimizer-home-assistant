# HACS Publication

## Release Boundary

The publication product is stable v1.5.x: learned appliances, native opt-in
orchestration, advisory EV plans, Ofgem benchmark and optional dashboard
templates. Do not advertise the v1.6/v1.7 history, analysis, import or AI betas
as stable. Publishing does not require retiring the separate Octopus
Intelligence reference app or promoting its unobserved replacement features.

## Repository Preflight (9 October 2026)

- Public, active repository; `main` is the default branch.
- Description, topics, enabled Issues, MIT licence and owner codeowner present.
- One packaged integration with manifest, configuration flow and local brand icon.
- `hacs.json` declares GB and hides the default branch; minimum HA is 2024.12.
- HACS and hassfest checks have no ignored errors.
- Stable runtime must match the release manifest; all new release checks must pass.
- New-installation, migration, dashboard and contribution guidance is present.
- A HACS catalogue submission has not yet been created.

The v1.5.1 preparation corrects the minimum version, prevents a second shared
learned-appliance hub and updates public documentation. The v1.5.3 update fixes
rejected firmware captures cancelling washes, exposes scheduling reasons and
refreshes programme selection with manual cooldown bypass. v1.5.4 fixes startup
when live scheduling confidence is not yet available. The owner has these fixes
in v1.7.0-beta.3, retaining the existing tariff-history features. Live checks
confirmed restored forecasts and programme options with unchanged learning and
91 history days. Observe the next real wash and learning increment before
catalogue submission. Check the actual CI
results and stable release immediately before submitting; this is not a claim
of testing every supported Home Assistant or appliance combination.

## Tomorrow's Submission

1. Confirm main's tests, minimum-version imports, HACS validation and hassfest
   are green and a full stable v1.5.4 GitHub release exists after those checks.
2. Sign in as repository owner `stevesherry123` and fork `hacs/default`.
3. Create a new branch from its `master` branch. Add
   `stevesherry123/load-optimizer-home-assistant` to the JSON `integration` list
   in alphabetical order; leave other entries unchanged.
4. Open an editable pull request to `hacs/default` and complete its current
   checklist truthfully. Submit only the stable integration, not a beta channel.
5. Monitor checks and respond to maintainers. Inclusion is reviewed, not instant;
   catalogue availability follows acceptance and a subsequent scan.

Use the current [official inclusion instructions](https://www.hacs.xyz/docs/publish/include/)
and [integration requirements](https://www.hacs.xyz/docs/publish/integration/).
The maintainers currently warn that new submissions can take months.

Until acceptance, users can install tomorrow through HACS Custom repositories,
category Integration, using the existing repository URL. This is distinct from
default-catalogue inclusion; do not announce that listing has already happened.

## Submission Summary

Suggested title: **Add Load Optimizer integration**.

Describe profile-weighted appliance learning/scheduling, opt-in native controls,
advisory EV planning and the regional Ofgem benchmark. Link the stable release
and green action run. Declare the GB benchmark, manual appliance YAML setup,
advisory-only EV control and optional dashboard setup clearly. Complete the
upstream PR template rather than using this summary as a replacement checklist.
