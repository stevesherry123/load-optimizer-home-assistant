# Static Security Review: 9 October 2026

## Scope

Reviewed the stable integration based on `cbab868`, packaged dashboard examples,
workflow permissions, migration adapters, external requests, storage and native
appliance command paths. Also inspected the beta-only tariff import/export and
AI boundaries separately; these features are not promoted into stable.

The review combined manual data-flow inspection, Python static scanning (Bandit
1.8.6), a redacted full Git-history credential scan (Gitleaks 8.30.1), unit tests
and isolated real Home Assistant 2024.12 authorization/privacy/import tests.
The initial history scan covered all local refs and 229 commits; no credentials
were detected. No private production configuration was copied into the report.

This is not penetration testing, a complete Home Assistant/platform dependency
audit, an independent certification or a guarantee that no vulnerabilities
remain. The manifest declares no additional Python package requirements. Core
and separately installed frontend integrations need their own updates/reviews.

## Findings And Remediation In v1.5.7

| Priority | Finding | Remediation |
| --- | --- | --- |
| High | Authenticated non-administrators could call destructive maintenance actions, including memory replacement and command-ownership changes. | Use Home Assistant's administrator-service wrapper for all six maintenance actions; test ordinary, unknown, administrator and trusted-system contexts. |
| Medium | Diagnostic downloads copied unredacted options and nested runtime details, including private raw YAML and identifiers. | Replace dumps with an explicit allowlist; omit titles, source/device/entity references, location settings, household schedules and arbitrary text. |
| Medium | Imports accepted malformed instances, unbounded/deep JSON and non-finite numbers; memory changed before a failed save and could race scans. | Validate bounded detached JSON off the event loop, serialize state operations, block active-capture replacement and commit memory only after successful persistence. Fail closed on malformed existing storage. |
| Medium | Invalid pasted planning intervals could stall execution; excessive horizons and invalid numeric source values were not consistently rejected. | Validate intervals/horizons at both planner entry points, validate finite prices and EV inputs, and cap EV candidate time coverage. |
| Medium | Native deactivation left an in-flight start task alive; an unknown door state did not block a start. | Cancel and await native execution before handing ownership back; clear requests and require a confirmed closed-door state. An already running wash is not stopped. |
| Low | Embedded credentials in log messages/exception strings could bypass key-based redaction. | Redact common value patterns in messages and context, bound recursion, and avoid raw exception traces/messages in active adapters. |
| Hardening | External benchmark responses/redirects had no explicit size/host bounds. No user-controlled source URL was exposed. | Permit only trusted HTTPS source hosts/ports, bounded redirects, 2 MiB decompressed documents, 16 tables and an overall lookup timeout. Retain TLS verification. |
| Hardening | Retired standalone add-on server and Supervisor HTTP code remained packaged, though not started by the integration. | Remove that unused runner/listener/network fallback. Keep the tested learning engine and in-process adapter. |
| Hardening | Validation actions floated on tags/branches and workflow permissions were implicit. | Pin action commits, use read-only contents permission, verify scanner binary checksum, and run mandatory static/credential scans in CI. |

## Verification And Residual Risk

- 221 unit tests cover learning, tariff planners, orchestration and hostile inputs.
- Real minimum-HA tests verify all six service permission checks, diagnostic
  allowlisting, malformed/disk-failed/concurrent/active-capture imports, and
  external URL/response boundaries without contacting live appliances.
- Existing real-HA imports, options, dashboard templates, device registration,
  reload and restart/identity checks remain required.
- Final security scans and HACS/hassfest must pass on the release commit before
  publication. The submission record links the actual successful runs.
- No intentional telemetry, public token endpoint, executable deserialization or
  integration-added inbound listener was identified in the stable runtime.
- Local HA entities and backups still contain household usage information by
  design. Authentication, automation editing, cloud appliance providers and
  optional frontend cards remain trusted/external boundaries.
- Credential scanners can miss nonstandard secrets; earlier diagnostic files
  cannot be made private retroactively. Review shared material and rotate any
  credential that was actually exposed.
- The beta additionally needs administrator checks on its response-bearing
  history/AI actions; this is handled on the beta line, not by releasing those
  features as stable.
