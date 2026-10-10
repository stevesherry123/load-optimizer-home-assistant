# Onboarding Development Plan

## Scope And Branches

The next development phase is safe community onboarding, not another supplier
integration or an automatic-control expansion. Documentation and isolated
clean-install tests are pushed on `docs/onboarding-clean-install` at `becd204`.
The first runtime slice is local on `feature/onboarding-validation`, based on
that documentation commit. Neither branch is merged into main or released.
The release version remains unchanged.

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
| Executable guides and minimal standard-card dashboard | Pushed, awaiting review | Fresh generic/Home Connect learning and persisted restart without imported memory |
| Shared bounded YAML parser and pre-save validation | Implemented locally | Invalid shape, duplicate IDs/keys/policies, non-finite values, bad references, flags and scheduling settings cannot save |
| Read-only source review before saving | Implemented locally | Show IDs, policy/tariff counts, missing sources and W/kWh warnings; cancellation changes nothing; saving enables no new control |
| Guided add/edit appliance form | Next implementation | Retain advanced YAML, immutable existing IDs, explicit removals, source selectors, no learning/model reclassification |
| Programme-policy editor | After appliance editor | Exact learned programme names, independent normal/negative permissions, explicit zero-as-unlimited labels, no implicit opt-ins |
| Selectable native controller target | Separate design/review | Remove ID 1 assumption only with safe identity migration, handover and no cross-appliance commands |
| Installation-specific starter dashboard | After editor | Use actual registered IDs; create an optional copy without overwriting custom dashboards |
| Community support pack and onboarding trial | Before broad promotion | Private-safe screenshots/issue forms; unfamiliar user completes documented flow |

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
- Saving valid options still reloads the runtime. Finish active captures first;
  the final confirmation blocks a known active capture or queued start without
  cancelling either. The check is repeated when the user retries saving.

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

The repeated free/negative-price scheduling fix remains at `e6ba6ca` on
`fix/negative-price-repeat-runs`, outside main. It deserves priority for beta
observation and a separately approved stable promotion; it must not disappear
behind onboarding work or be merged incidentally with it.
The stored scheduling diff was reviewed and its 235 unit tests rerun successfully
on 10 October, without changing that checkout. This is not evidence of today's
live automatic cycles or permission to promote/publish it.

The tariff history/import/AI branches still have their own next-day/provider,
dashboard and historical-rebasing gates. The previous HACS catalogue request
also remains a separate maintainer process; this local task does not establish
its current acceptance state or alter the submission.
