# Security Policy

## Supported Versions

Use the latest stable v1.5.x release for public installations. Security fixes are
also carried to the active beta branch, but beta functionality is experimental.
Older integration releases do not receive separate maintenance fixes. The Home
Assistant minimum in `hacs.json` is a compatibility floor, not a recommendation
to run an obsolete core version; use a supported, updated Home Assistant release.

## Report Privately

Use [GitHub private vulnerability reporting](https://github.com/stevesherry123/load-optimizer-home-assistant/security/advisories/new).
If that form is unavailable, open a public issue containing only a request for a
private contact route. Do not include exploit details, credentials, home URLs,
private appliance configuration or unredacted diagnostics in that public issue.

Include affected versions, impact, the smallest reproducible example using
synthetic data, and any proposed fix. Do not test against other people's Home
Assistant instances or physical appliances. No response-time guarantee is made.

## Boundaries

- Home Assistant controls authentication, entity permissions, remote access and
  secure storage. Keep its authentication and host protections enabled.
- Maintenance actions require an administrator. HA's trusted system automation
  context is still allowed; access to editing automations is a trusted capability.
- Household schedules and learned profiles remain sensitive, even without a
  token. Review any material before publishing it.
- The integration is not a safety interlock. Appliance hardware protections must
  remain in place. EV planning is advisory and does not control a charger.
- See [privacy](docs/privacy.md) and the
  [2026-10-09 review](docs/security-review-2026-10-09.md) for scope and limitations.
