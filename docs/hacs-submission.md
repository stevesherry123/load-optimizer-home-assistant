# HACS Catalogue Submission

The owner authorized submission on their behalf on 9 October 2026, superseding
the earlier prepare-only request. The stable submission is v1.5.7 after its
security review. Custom-repository installation already works; catalogue
acceptance is a separate review. The submission URL will be recorded here after
the release and upstream pull request are created.

## Submission Procedure

1. Read the [publishing guide](https://www.hacs.xyz/docs/publish/start/) and
   [inclusion instructions](https://www.hacs.xyz/docs/publish/include/).
2. Fork [hacs/default](https://github.com/hacs/default) to your personal account.
   Create a new branch from its current `master`, named `add-load-optimizer-v1.5.7`.
3. Edit the root JSON file named `integration`, inserting
   `stevesherry123/load-optimizer-home-assistant` in alphabetical order. Keep the
   surrounding JSON valid, including commas, and change no other entries.
4. Open a pull request from that branch to `hacs/default:master`. Leave
   **Allow edits by maintainers** enabled. Suggested title:
   **Add Load Optimizer integration**.
5. Use the current upstream template. The prepared text below follows the
   template checked on 9 October 2026. The publishing guide has been reviewed;
   verify every statement and the release/check status before submitting.
6. Do not request reviewers. Respond to checks or maintainer questions; the
   listing appears only after acceptance and the next catalogue scan.

## Prepared Pull Request Text

```markdown
## Checklist

- [x] I've read the [publishing documentation](https://hacs.xyz/docs/publish/start).
- [x] I've added the [HACS action](https://hacs.xyz/docs/publish/action) to my repository.
- [x] (For integrations only) I've added the [hassfest action](https://developers.home-assistant.io/blog/2020/04/16/hassfest/) to my repository.
- [x] The actions are passing without any disabled checks in my repository.
- [x] I've added a link to the action run on my repository below in the links section.
- [x] I've created a new release of the repository after the validation actions were run successfully.

## Links

Link to current release: <https://github.com/stevesherry123/load-optimizer-home-assistant/releases/tag/v1.5.7>
Link to successful HACS action (without the `ignore` key): <https://github.com/stevesherry123/load-optimizer-home-assistant/actions/runs/37954574738/job/113901706117>
Link to successful hassfest action (if integration): <https://github.com/stevesherry123/load-optimizer-home-assistant/actions/runs/37954574738/job/113901705903>

<!-- tid:73253df5-5376-4e68-8c16-b234da6a2de3 -->
```

## Release Scope And Evidence

Stable v1.5.7 provides learned appliance profiles and profile-weighted scheduling,
opt-in native appliance orchestration, advisory EV charging plans, a configurable
regional Ofgem comparison benchmark, and optional dashboard templates. It does
not introduce direct EV charger control. Appliance setup currently uses YAML
inside the configuration flow. The benchmark is GB-specific; `hacs.json`
declares `country: GB`. Rich charts and tile colouring use optional frontend
cards; core operation does not require them.

The security code merged in `6e4791814f6499d59eba622867bb8aac07550b13`.
The [full validation run](https://github.com/stevesherry123/load-optimizer-home-assistant/actions/runs/37954574738)
checks 221 unit tests, actual minimum Home Assistant 2024.12 imports and forms,
dashboard templates, actual appliance/orchestration device registration and EV
options/reload/restart persistence, service authorization, diagnostic privacy,
safe imports and HTTP boundaries, plus mandatory Bandit/Gitleaks scans, HACS and
hassfest. The [security review](security-review-2026-10-09.md) records findings,
fixes and limitations. v1.5.7 supersedes v1.5.6 for this submission.
Isolated downgrade/re-upgrade previously retained registered identities.
The owner's physical MixedLoad wash completed normally on 9 October, with its
learning increment confirmed. These checks do not imply testing every appliance
model or every Home Assistant version.

Advanced tariff history, historical comparisons, portable import and optional
AI summaries remain experimental v1.6/v1.7 work and are not part of this stable
submission. Do not present them as released stable functionality.
