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
- The owner authorized HACS submission on 9 October, after security review and
  the validated v1.5.7 release. Track its actual status in `hacs-submission.md`.

The v1.5.1 preparation corrects the minimum version, prevents a second shared
learned-appliance hub and updates public documentation. The v1.5.3 update fixes
rejected firmware captures cancelling washes, exposes scheduling reasons and
refreshes programme selection with manual cooldown bypass. v1.5.4 fixes startup
when live scheduling confidence is not yet available. The owner has these fixes
in v1.7.0-beta.3, retaining the existing tariff-history features. Live checks
confirmed restored forecasts and programme options with unchanged learning and
91 history days. The subsequent physical MixedLoad wash completed on 9 October
at 13:36 BST: dishwasher learning increased to 114 total runs and MixedLoad to
4 runs at 61% confidence. Completion was confirmed, the queue cleared and no
active captures or integration errors remained. The real-wash gate is passed.
The separate v1.5.5 EV editor passed isolated real minimum-HA browser/options,
reload, persisted restart, stable downgrade and re-upgrade checks with unchanged
entry, device and entity identities. Expanded minimum-HA testing then found a
newer-only registry API in appliance/orchestration device linking. Stable v1.5.6
corrects that compatibility issue; 209 unit tests and actual minimum-HA device
registration pass. v1.5.7 adds the completed static security review, private
diagnostic allowlisting, administrator-only maintenance, bounded/atomic imports,
control/HTTP safeguards and mandatory security scans. All five code-validation
jobs and 221 unit tests pass. v1.5.7 is the submission release. Check the actual CI
results and stable release immediately before submitting; this is not a claim
of testing every supported Home Assistant or appliance combination.

## Catalogue Submission

Submitted on 9 October: [hacs/default#11744](https://github.com/hacs/default/pull/11744).
All upstream catalogue validation and lint checks passed. The request remains
open in the maintainer review queue; submission is not catalogue acceptance.
Stable v1.5.7 was published from `28f4380b0b6a596227dc1159aab1bb41dbd0ecac`
after [all five release checks passed](https://github.com/stevesherry123/load-optimizer-home-assistant/actions/runs/37954979544).

The owner now authorizes submission on their behalf. This supersedes the earlier
prepare-only instruction. Use [the submission record](hacs-submission.md) for
the current upstream checklist, exact release/check links and submission status.

1. Confirm main's tests, minimum-version imports, HACS validation and hassfest
   are green and a full stable v1.5.7 GitHub release exists after those checks.
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

The owner now runs v1.7.0-beta.4, which carries the stable editor and registry
fix without removing beta history/import. Live restart acceptance preserved all
222 entity/device identities, the exact dashboard configuration, learning totals
114 / 189 / 46, MixedLoad 4 runs / 61%, and 91 history days. Forecasts, EV form
defaults and focused logs passed. This does not promote experimental analysis
into the stable v1.5.7 submission. Security fixes also carry to the published
[v1.7.0-beta.5](https://github.com/stevesherry123/load-optimizer-home-assistant/releases/tag/v1.7.0-beta.5),
from `88e23d4c628f428f998429cfd0d86b269d1915c6` after
[all five beta checks passed](https://github.com/stevesherry123/load-optimizer-home-assistant/actions/runs/37955524653).
Its 271 unit tests and isolated real-HA permission tests include the beta-only
history/AI actions. Publishing it did not install or restart the owner's HA.

Until acceptance, users can install through HACS Custom repositories,
category Integration, using the existing repository URL. This is distinct from
default-catalogue inclusion; do not announce that listing has already happened.

## Submission Summary

Suggested title: **Add Load Optimizer integration**.

Describe profile-weighted appliance learning/scheduling, opt-in native controls,
advisory EV planning and the regional Ofgem benchmark. Link the stable release
and green action run. Declare the GB benchmark, manual appliance YAML setup,
advisory-only EV control and optional dashboard setup clearly. Complete the
upstream PR template rather than using this summary as a replacement checklist.
