# Release Channels And HACS

## What HACS Does

HACS helps users discover this repository, download integration files and see
available updates. The code and releases remain hosted on GitHub. Downloading
the files, restarting Home Assistant and configuring Load Optimizer are separate
steps. Catalogue inclusion is not Home Assistant Core inclusion or a security
certification.

## What Reaches Users

| Maintainer action | Normal stable users | Opted-in beta testers |
| --- | --- | --- |
| Push to a feature/test branch | No stable update | No release update merely from the push |
| Merge to `main` | No new release update | No new release update |
| Create a Git tag only | Not our publication mechanism | Not our publication mechanism |
| Publish a GitHub prerelease | Not offered as stable | Eligible for prerelease updates |
| Publish a full stable GitHub release | Eligible for a stable update | Also available |

Users ordinarily choose when to download an update. Their own Home Assistant
automation can call `update.install`, so a user's automatic-update policy is
outside this repository's control. Downloaded Python integration changes need a
Home Assistant restart before they take effect.

The prerelease switch enables consideration of beta releases; it is not a
separate installation or an independent channel for every beta branch. Use a
separate test Home Assistant instance for isolated development.

Branch names do not enforce safety. Publishing a full stable release from a
test branch would still expose it to stable users. Our policy is to develop and
test separately, then merge approved changes to `main` and publish a stable
release from the exact green commit, with matching manifest/runtime versions.
Never move a tag that users have already installed.

`hide_default_branch: true` keeps `main` out of the normal version picker. It is
not access control: the repository and beta branches are public, and advanced
users can explicitly install a public branch or full commit. Development is
isolated from normal updates, not secret.

## Branches Retained After Cleanup

- `main`: stable product and public documentation.
- `beta/tariff-analysis-v1.6`: deterministic history/analysis, draft PR #4.
- `beta/tariff-import-narrative-v1.7`: stacked import/optional AI development,
  draft PR #5, based on the analysis work.

The two beta branches have distinct promotion gates. They are not both installed
side by side. No unfinished beta features were merged into stable by cleanup.
The [cleanup record](branch-cleanup-2026-10-09.md) preserves retired branch tips.

## What Users Read

The README is the main entry point in GitHub and HACS. HACS retrieves versioned
documentation: normally the installed version's README, or the latest available
version for a repository not yet installed. Changing only `main` does not rewrite
the README in an existing release.

Users also see release notes and can follow the setup, dashboard, migration,
privacy and support guides. Keep these consistent with the stable feature set;
label experimental and historical documents clearly. Corrections on `main`
enter HACS's release-specific README with the next published release. Do not
replace an existing tag merely to update its documentation.

## Catalogue Acceptance

The request is [hacs/default#11744](https://github.com/hacs/default/pull/11744),
submitted by the owner on 9 October 2026. Catalogue validation and lint passed;
maintainer review is pending. A merged request is the acceptance signal. The
listing follows a scheduled catalogue scan, so it is not instantaneous.

The owner's GitHub account was verified as subscribed to this request. GitHub
can notify through its inbox, mobile app or email according to account settings.
Check participating notifications if email is wanted. The request page remains
the authoritative status; a closed-but-unmerged request is not acceptance.
Do not send routine status comments, request reviewers or open duplicates while
waiting. Continue normal repository development and respond to maintainer
questions when asked.

## Statistics And Privacy

- **GitHub traffic:** Insights > Traffic shows recent repository views, unique
  visitors, full clones and referral information. The standard window is 14
  days; these are interest/development signals, not installed-user totals.
- **Download counts:** uploaded release assets have GitHub download counters,
  which HACS can use. Stable v1.5.7 has no uploaded assets and uses repository
  contents, so it has no useful release-asset counter. Automatically generated
  source archives do not supply the same asset count. Zero or missing HACS
  downloads must not be interpreted as zero installations.
- **Optional future packaging:** a tested release ZIP could provide a rough
  download counter. Re-downloads, upgrades, bots and manual downloads mean it
  would still not count unique people or active installations. No packaging
  change or tracking mechanism was added by this documentation review.
- **Home Assistant analytics:** users who independently opt into HA usage
  analytics can contribute aggregated custom-integration/version counts. If
  `load_optimizer` appears in the public custom-integrations dataset, that can
  provide an opt-in sample, not the total population. It was absent when checked
  on 9 October; absence does not establish zero users.
- **Who installed it:** neither public download counters nor public HA analytics
  disclose named users or their household data. People who voluntarily open
  issues or discussions identify themselves, not everyone who installed it.

Load Optimizer adds no telemetry or phone-home install reporting. Home
Assistant's own analytics are a separate, user-controlled setting; this
integration does not enable or change it.

## Sources

- [HACS integration releases](https://www.hacs.xyz/docs/publish/integration/)
- [HACS prerelease switch](https://www.hacs.xyz/docs/use/entities/switch/)
- [HACS update action and explicit versions](https://www.hacs.xyz/docs/use/entities/update/)
- [HACS catalogue inclusion](https://www.hacs.xyz/docs/publish/include/)
- [HACS versioned documentation/download implementation](https://github.com/hacs/integration/blob/main/custom_components/hacs/repositories/base.py)
- [GitHub notifications](https://docs.github.com/en/subscriptions-and-notifications/concepts/about-notifications)
- [GitHub traffic](https://docs.github.com/en/repositories/viewing-activity-and-data-for-your-repository/viewing-traffic-to-a-repository)
- [GitHub release-asset counters](https://docs.github.com/en/rest/releases/assets)
- [Home Assistant opt-in analytics](https://www.home-assistant.io/integrations/analytics/)
