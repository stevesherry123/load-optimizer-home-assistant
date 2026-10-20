# HACS Publication

## Release Boundary

The publication product is stable v1.5.x: learned appliances, native opt-in
orchestration, advisory EV plans, Ofgem benchmark and optional dashboard
templates. Do not advertise the combined `beta/next` history, analysis, import
or AI features as stable. Publishing does not require retiring the separate Octopus
Intelligence reference app or promoting its unobserved replacement features.

The approved 19 October deployment installed and verified v1.7.0-beta.9;
see the [deployment acceptance record](power-up-pricing.md#deployment-acceptance-19-october-2026).
Later dashboard/explanation changes remain unreleased. Beta code is
separate from published stable v1.5.7. The only active branches are
`main` and `beta/next`; merging and stable publication require separate approval.
See [release channels](release-channels.md) for the current branch/release model.
The dated acceptance evidence below is historical, not a direction to open a
new HACS submission or install an older beta.

## Publication Review: 19 October 2026

The README and linked setup, compatibility, control, EV, dashboard,
troubleshooting and privacy guides describe the stable product separately from
beta development. Installation, source configuration, completed learning,
recommendation eligibility and optional control activation are distinct steps.
The documented examples are executable tests, not borrowed household settings.

Keep the following boundaries in any public announcement:

- HACS catalogue review is still pending; custom-repository installation works
  independently. Do not open another submission or post progress comments.
- Stable v1.5.7 does not include beta tariff history/AI or the beta.9 Power Up and
  delayed-start changes. A branch push does not deploy them to existing users.
- EV charging is advisory; native start control is limited to the documented
  ID `1` Home Connect dishwasher. Nothing starts automatically after setup.
- Dashboards are optional templates. Custom copies are not automatically
  replaced; chart and colour enhancements have their documented dependencies.
- An unfamiliar-user onboarding trial, privacy-safe screenshots and issue forms
  remain open. Automated examples and the owner's completed washes do not
  substitute for testing another household's setup.
- Before promoting the combined beta, observe natural forecast revision/tail
  handling and repeated real free-price execution. Beta.9 deployment is verified.
  Structured AI
  selection has passed one real-provider replay, not a new live service test
  after installation. Do not imply approval for another paid call.

No release, production configuration change or upstream HACS edit is performed
by this documentation review. See [the roadmap](roadmap.md) for remaining work.

## Repository Preflight (9 October 2026)

- Public, active repository; `main` is the default branch.
- Description, topics, enabled Issues, MIT licence and owner codeowner present.
- One packaged integration with manifest, configuration flow and local brand icon.
- `hacs.json` declares GB and hides the default branch; minimum HA is 2026.10.2.
- Octopus sources require integration 19.2.1 or newer, checked against entity
  ownership at setup (renamed entities are supported). Generic sources remain optional.
- HACS and hassfest checks have no ignored errors.
- Stable runtime must match the release manifest; all new release checks must pass.
- New-installation, migration, dashboard and contribution guidance is present.
- The owner authorized HACS submission on 9 October, after security review and
  the validated v1.5.7 release. Track its actual status in `hacs-submission.md`.

The v1.5.1 preparation corrects the minimum version, prevents a second shared
learned-appliance hub and updates public documentation. The v1.5.3 update fixes
rejected firmware captures cancelling washes, exposes scheduling reasons and
refreshes programme selection with manual cooldown bypass. v1.5.4 fixes startup
when live scheduling confidence is not yet available. Those fixes were installed
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

## Catalogue Submission Record (9 October 2026)

Submitted on 9 October: [hacs/default#11744](https://github.com/hacs/default/pull/11744).
All upstream catalogue validation and lint checks passed. The request remains
open in the maintainer review queue; submission is not catalogue acceptance.
Stable v1.5.7 was published from `28f4380b0b6a596227dc1159aab1bb41dbd0ecac`
after [all five release checks passed](https://github.com/stevesherry123/load-optimizer-home-assistant/actions/runs/37954979544).

The owner authorized that submission on their behalf, superseding the earlier
prepare-only instruction. Use [the submission record](hacs-submission.md) for
the upstream checklist, exact release/check links and submission status. The
steps below record the submission procedure; do not repeat it while #11744 is
pending or post routine progress comments to the upstream request.

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

On 9 October the owner installed v1.7.0-beta.4, carrying the stable editor and registry
fix without removing beta history/import. Live restart acceptance preserved all
222 entity/device identities, the exact dashboard configuration, learning totals
114 / 189 / 46, MixedLoad 4 runs / 61%, and 91 history days. Forecasts, EV form
defaults and focused logs passed. This does not promote experimental analysis
into the stable v1.5.7 submission. Security fixes also carry to the published
[v1.7.0-beta.5](https://github.com/stevesherry123/load-optimizer-home-assistant/releases/tag/v1.7.0-beta.5),
from `88e23d4c628f428f998429cfd0d86b269d1915c6` after
[all five beta checks passed](https://github.com/stevesherry123/load-optimizer-home-assistant/actions/runs/37955524653).
That beta's 271 unit tests and isolated real-HA permission tests include the beta-only
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
