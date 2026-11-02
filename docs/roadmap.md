# Roadmap

This is a high-level feature roadmap, not a release commitment. Use the installed
release's README and changelog for available features; main can contain unreleased
work. Detailed internal delivery plans and acceptance diaries are maintained
separately from the public product documentation.

## Priorities

- Make appliance and programme-policy editing easier while preserving stable
  identities, existing learning and explicit automatic-control opt-ins.
- Improve installation-specific starter dashboards and new-user onboarding.
- Continue decomposing the compatibility engine behind native HA entities without
  changing learned data or appliance safety checks.
- Evaluate tariff history, deterministic comparisons and optional AI summaries
  independently from the stable appliance scheduling path.
- Refine EV planning and assess optional charging control through separately
  tested development work; advisory planning does not itself operate a charger.
- Explore provider-neutral solar, storage and lower-carbon scheduling inputs.

## Acceptance boundaries

Promotions need representative missing-data, restart, migration, timezone and
physical-control acceptance where applicable. A published plan, green unit test
or catalogue listing is not evidence that every appliance/provider is supported.
Do not remove legacy functionality until an approved replacement passes its gates.

See [architecture](architecture.md), [clean-install acceptance](onboarding-acceptance.md),
[runtime safety](runtime-safety.md), [release channels](release-channels.md) and
[GitHub Issues](https://github.com/stevesherry123/load-optimizer-home-assistant/issues)
for public behaviour, testing and contribution context.
