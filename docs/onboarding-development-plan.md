# Onboarding Development Plan

## Scope And Branches

The next development phase is safe community onboarding, not another supplier
integration or an automatic-control expansion. Documentation and isolated
clean-install tests from `becd204` and the initial runtime validation slice
were merged to main at `c16b9e9` through
[PR #16](https://github.com/stevesherry123/load-optimizer-home-assistant/pull/16).
They are unreleased, not separate merge tasks. Guided editing remains future
work; the release version is unchanged.

Do not fold either tariff beta into this work. Keep release publication, live
installation/restarts and physical appliance commands separately approved.

## Targeted Review Findings

1. The learned-appliance setup/options form saved input without checking its
   shape or runtime conversions. Invalid numbers could break the next reload;
   duplicate IDs could associate multiple appliances with the same memory.
2. The compatibility parser interpreted only a subset of YAML. Flow mappings,
   comments and policy-list indentation could produce different settings from
   the user's intended document. Preflight and runtime must share one parser.
3. Programme flags were passed through `bool(value)`: a quoted `"false"` is
   truthy. Reject ambiguous flag types in new edits, and use fail-closed boolean
   coercion at runtime for previously saved textual false/unknown values.
4. Missing sources and W/kWh mistakes were discovered only after configuration.
   Temporary unavailability must be a warning, not a permanent setup blocker.
5. A pasted legacy options block can contain reset instructions. An ordinary
   appliance edit must not silently reset learning.

These findings are addressed by the first slice. This is a targeted
configuration/onboarding review, not a new claim that every project component
has been independently security-audited.

## Delivery Order

| Slice | Status | Acceptance |
| --- | --- | --- |
| Executable guides and minimal standard-card dashboard | On main, unreleased | Fresh generic/Home Connect learning and persisted restart without imported memory |
| Shared bounded YAML parser and pre-save validation | On main, unreleased | Invalid shape, duplicate IDs/keys/policies, non-finite values, bad references, flags and scheduling settings cannot save |
| Read-only source review before saving | On main, unreleased | Show IDs, policy/tariff counts, missing sources and W/kWh warnings; cancellation changes nothing; saving enables no new control |
| Guided add/edit appliance form | Next implementation | Retain advanced YAML, immutable existing IDs, explicit removals, source selectors, no learning/model reclassification |
| Programme-policy editor | After appliance editor | Exact learned programme names, independent normal/negative permissions, explicit zero-as-unlimited labels, no implicit opt-ins |
| Selectable native controller target | Separate design/review | Remove ID 1 assumption only with safe identity migration, handover and no cross-appliance commands |
| Installation-specific starter dashboard | After editor | Use actual registered IDs; create an optional copy without overwriting custom dashboards |
| Community support pack and onboarding trial | Before broad promotion | Private-safe screenshots/issue forms; unfamiliar user completes documented flow |

The 13 October [ledger and guided-setup design](physical-cycle-ledger-design.md)
records the proposed forms, removal semantics and the separately prioritized
physical-cycle counter. It is a discussion draft, not an implemented editor or
approval to change automatic accounting. PR #17's command-time repair now has
322 passing unit tests and isolated minimum-HA acceptance; merge approval is
separate. Agree the ledger design before its shadow implementation.

The guided editor should update one appliance in the existing list rather than
replace the hub or allocate a new identity when its name changes. Existing
thresholds, policies, capture behaviour and unknown extension fields must survive
an unrelated edit. Adding a generic appliance must not silently invent policy
permissions. Programme-policy changes must be visibly separate from a physical
start action. Confirm removal semantics before implementing deletion.

## First-Slice Boundaries

- Parse safe YAML/JSON with duplicate-key rejection, 128 KiB input, depth/node
  limits, 64 appliances and 128 policies per appliance; no aliases or custom tags.
- Preserve zero-prefixed IDs and unquoted HH:MM as literal values. Keep legacy
  wrapped options and split-field precedence, without writing a new document.
- Cache only four bounded parses in memory and return independent copies.
- Validate in HA's executor. Do not call suppliers, AI or appliance services.
- Do not rewrite a learning store or add new automatic-control defaults.
- Validate on explicit setup/edit, not as a learning-data migration. The runtime
  parser remains tolerant of an invalid document by reporting no configuration.
- Source warnings are a snapshot, not proof of future tariff completeness,
  correct price-unit selection or successful remote activation.
- Saving valid options still reloads the runtime. All learned-hub settings
  sections block a known active capture or queued start without cancelling
  either. Submitted values remain in the form, and the check repeats on retry.
  EV settings use their independent lifecycle.

## Verification And Release Gates

For this slice, run the full unit suite, real minimum-HA setup/options and schema
serialization, failed/cancelled edits, learning/identity preservation, reload and
restart, dashboard templates, security smoke tests and Bandit. The minimum-HA
onboarding test intercepts device calls and mocks HTTP listeners; no real login,
network supplier/AI request or physical wash is needed.

Before promotion: review the diff, run remote CI/HACS/hassfest through a PR and
complete desktop/mobile form inspection and an unfamiliar-user trial. Verify
representative migrated configuration as well as the synthetic examples. Any
stable release/version bump and live deployment require separate approval.

## Other Release Work Still Separate

The earlier repeated free/negative-price fix at `e6ba6ca` is being selectively
carried on `fix/negative-price-repeat-safety` against current main, with fresh
source checks, exact-programme command-time repricing, retry explanations and
finite-history protection. See
[repeat repair acceptance](negative-price-repeat-repairs.md). Its isolated
results are not evidence of today's live cycles or permission to merge/release.

The tariff history/import/AI branches still have their own next-day/provider,
dashboard and historical-rebasing gates. The previous HACS catalogue request
also remains a separate maintainer process; this local task does not establish
its current acceptance state or alter the submission.
