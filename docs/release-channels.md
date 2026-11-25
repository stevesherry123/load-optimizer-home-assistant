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
Never move a tag that users have already installed. Public prereleases form one
update stream: each new beta must advance all published release versions. Do
not publish a lower-version beta from a parallel branch after a higher-version
trial. The release preflight rejects this ordering error.

`hide_default_branch: true` keeps `main` out of the normal version picker. It is
not access control: the repository and beta branches are public, and advanced
users can explicitly install a public branch or full commit. Development is
isolated from normal updates, not secret.

## Owner trials through Home Assistant Marketplace

The owner's HA 2026.11 installation uses the built-in **Marketplace** update
provider. Do not infer HACS from an entity's name or historical installation.
Read its entity-registry `platform` and config-entry domain before choosing an
installation procedure. HACS-specific controls do not apply to Marketplace.

Installing a full commit through `update.install` proves only that the files
were downloaded. A raw commit is not a comparable release version. On the stable
channel, HA can offer the older stable release as an update; a subsequent
ordinary install can replace the trial code. The loaded manifest's version alone
also does not prove which source revision was installed.

For this owner trial:

1. Prepare a numbered beta with matching manifest, runtime version and changelog.
   Run `dev/check_beta_release.py` against the exact green commit. A draft is not
   a published release and must not be treated as an available update.
2. Publish the approved GitHub prerelease, verify the immutable tag's commit and
   verify the source package against the committed files. Do not move an old tag.
3. Enable beta releases for this repository through Marketplace's supported
   repository control. This is one repository's update policy, not an isolated
   channel for a particular feature branch. Verify the offered version first.
4. With idle appliances and no pending command, create a recoverable backup,
   install the exact release tag and check every downloaded component file.
5. Restart HA and verify entries, entity identities, learned data and controls.
   Then run the read-only owner channel check below. Require installed version,
   loaded manifest, repository identity, beta setting and default install target
   to agree, with no pending restart and no update offered. An off update entity
   alone is insufficient because a direct generic service call still has a target.
6. Repeat readback after the other update work and a Marketplace refresh, then
   correlate the next physical wash with that installed build. Installation,
   continued version retention and physical acceptance are separate evidence.
   New execution snapshots record `build_version`; old snapshots without it
   remain readable and must not be retroactively attributed to a newer build.

```sh
# Credentials are supplied by the environment; this script never installs,
# changes channel settings, restarts HA or prints its token.
python dev/check_owner_channel.py v1.7.0-beta.12 --output .local/owner-channel.json
```

Use `LOAD_OPTIMIZER_HA_URL` and `LOAD_OPTIMIZER_HA_TOKEN` for authenticated reads,
or `--snapshot FILE` for offline checks. Keep credentials and household evidence
out of Git. The redacted output contains release metadata only. File hashes and
learning preservation still require their separate checks.

Source: [HA 2026.11.2 Marketplace update service](https://github.com/home-assistant/core/blob/2026.11.2/homeassistant/components/marketplace/update.py),
[repository version/channel implementation](https://github.com/home-assistant/core/blob/2026.11.2/homeassistant/components/marketplace/repositories/base.py),
and [supported repository WebSocket controls](https://github.com/home-assistant/core/blob/2026.11.2/homeassistant/components/marketplace/websocket/repository.py).

## Development Branches

`main` may contain unreleased work. Feature and experimental branches have their
own acceptance gates; their names are not release metadata or a promise of safe
side-by-side installation. Use published tags and release notes to identify the
supported installed scope, not a historical branch-cleanup inventory.

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

Load Optimizer was approved and added to the default HACS catalogue on
2 November 2026 through
[hacs/default#11744](https://github.com/hacs/default/pull/11744).
New users should search for **Load Optimizer** in HACS; custom-repository setup
is a fallback if their catalogue has not refreshed. Existing custom-repository
users do not need to remove their configured integration or re-import learning.

A merged request is the acceptance signal. Catalogue distribution follows a
scheduled scan, so inclusion is not instantaneous after a merge.

GitHub can notify subscribers through its inbox, mobile app or email according to
their account settings. The request page remains
the authoritative status; a closed-but-unmerged request is not acceptance.
Do not send routine queue-status comments or open duplicates while waiting.
Follow the maintainer's instructions when responding to requested changes or
returning a submission for review. Normal repository development can continue.

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
