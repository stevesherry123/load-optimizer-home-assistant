# Physical-Cycle Ledger And Guided Setup

Status: discussion draft, 13 October 2026. No ledger, counter migration, new
entity or guided editor is implemented by this document. Based on the PR #17
review branch; its repairs and open command-time finding remain separate gates.

## Purpose

Separate three questions which currently share incomplete evidence:

1. Did a physical appliance cycle happen, and what was its outcome?
2. Was its power capture good enough to update a learned programme model?
3. Has that programme used its automatic free/negative-window allowance?

A real wash with a missing power sample must not disappear from operational
history merely because learning correctly rejects its profile. A firmware-update
power capture must not become a wash, increment a physical completion counter,
consume a confirmed-cycle allowance or cancel a queued wash.

Preserve existing learned models, totals, programme names, thresholds, devices,
entity IDs, dashboards and explicit opt-ins. The ledger is additive, not a
replacement import or a relabelled learning count.

## Existing Evidence And Limits

- Learned programme models retain ten recent cycles. PR #17 conservatively
  pauses finite caps when that evidence cannot establish window coverage.
- Native orchestration retains ten request outcomes, not a complete wash ledger.
- Operation-state Run transitions provide independent running evidence. Current
  running-to-idle handling can also accept learned completion evidence; it is
  not sufficient by itself to distinguish success, cancellation and interruption.
- Physical native control currently targets appliance 1/Home Connect. The
  ledger identity model should support other appliances without pretending their
  control adapters already exist.
- Final review found no exact-programme tariff revalidation after command delays.
  Resolve that independently before live repeat-scheduling acceptance; do not
  wait for a new ledger to repair an execution-time price check.

## Proposed Record

Use a separate versioned Home Assistant Store, owned by the existing learned-hub
entry. Key each appliance by entry identity plus its immutable instance ID, never
by display name, a mutable source entity ID or list position.

Each cycle record has a stable cycle ID, canonical programme key when known,
request ID when available, origin (automatic/manual/external/unknown), observed
start/end in UTC, evidence type and operational outcome. Record learning linkage
and exclusion reason separately; learning is not the source of physical truth.

Keep command reservations distinct from observed cycles. A persisted reservation
has a request ID, intended programme, requested mode and quota context. It is
not a completion counter. Retries/fallbacks for the same request share it.

Store coverage boundaries and unresolved evidence explicitly. No assumed
historical physical total is copied from a learned total. If helpful, expose the
old learned count alongside the independently verified count since activation.

## Lifecycle And Idempotency

1. Under one per-appliance command lock, re-read exact-programme permission,
   confidence, actual-time tariff fit, full-cycle no-run windows, readiness and
   quota evidence. A newer unrelated recommendation cannot authorize this run.
2. Persist the reservation before sending a start-capable command. Storage
   failure must prevent a new automatic start, not permit an unrecorded one.
3. A genuine adapter Run transition attaches to that reservation or creates an
   externally initiated cycle. Repeated events attach to the same cycle ID.
4. Record physical running independently of power capture. Adapter-specific
   completion evidence finalizes success exactly once. Fault, cancellation,
   lost observation and restart ambiguity retain their distinct outcomes.
5. No confirmed start means no completed cycle. A sent-but-unconfirmed command
   remains unresolved until reliable evidence or explicit administrator action
   resolves it; do not automatically free its reservation on a short timeout.

Persist before publishing counters. A reload/restart reconciles open records
before automatic evaluation. Never infer successful completion solely because
Home Assistant restarted while the appliance was no longer running.

Unconfigured/unavailable operation evidence can still permit advisory learning,
but cannot claim verified physical quota coverage. Do not silently enable a
generic appliance controller to fill that gap.

## Proposed Counting Rules

These are recommendations for approval, not new behaviour:

- A physical completed-cycle total increments only on verified successful
  completion. Rejected learning does not reduce it. Show observation start date.
- Automatic allowance accounting reserves in-flight work and consumes one
  allowance once genuine running is confirmed, even if the wash later faults
  or is cancelled. This prevents repeated failed starts from bypassing a cap;
  it is deliberately different from the successful-completion counter.
- Confirmed manual/external cycles affect subsequent automatic allowances, but
  an explicit manual start is not vetoed by automatic cooldown or quota rules.
  Existing physical safety checks remain mandatory.
- Preserve per-programme, per-contiguous nonpositive-price-window limits. Zero
  remains explicitly unlimited. A positive-price gap separates windows.
- Preserve current overlap semantics unless agreed otherwise: a cycle spanning
  two distinct windows can consume an allowance in each, once per cycle/window.
  An active reservation is included conservatively, never counted twice when
  observed running replaces the reservation.
- Unknown programme/outcome cannot be credited to an arbitrary programme. Mark
  coverage uncertain and pause affected finite automatic allowances; do not
  guess from whichever programme is now selected on the appliance.

Keep actual cycle intervals and tariff provenance rather than assigning only a
temporary window ID. Tomorrow's publication and revised prices can extend,
merge or split windows. Re-evaluate overlap in UTC against current authoritative
periods, preserving original evidence and disclosing revisions. Local timezone
and daylight-saving changes affect display, not elapsed-time counting.

## Migration, Retention And Recovery

Start with read-only shadow collection: existing learning and caps stay in
control while the ledger reports differences. There is no immediate historical
backfill and no automatic switch from learned to physical quota semantics.

Maintain a coverage frontier. Only enforce from the ledger when the relevant
window is fully observed and reservations are reconciled. Otherwise retain the
existing conservative learned-history fallback or pause; never add both counts
for the same cycle. Any future import needs a preview, provenance and explicit
approval, and may import only verified physical evidence.

Bound retention by age and count, with explicit truncation/coverage markers.
Do not delete unresolved cycles or current-window evidence to meet a limit;
report capacity pressure and pause new automatic work if safe persistence is
impossible. Propose a 90-day/500-terminal-cycle per-appliance limit for review,
not an unbounded log or an implementation default agreed in advance.

Downgrades must leave the additive store intact. Existing stable versions do
not understand or enforce the new ledger, so rollback documentation must state
that limitation and require automatic control to be disabled first. Upgrade
must reconcile partial records without rewriting learning or allocating IDs.

Corruption, unsupported schema and failed writes must be visible, must not
silently reset totals, and must pause affected automatic starts. Preserve the
original data for recovery. Do not stop an already running appliance.

## Dashboard And Privacy

Add operational completion, allowance used/reserved, observation coverage and
last outcome as separate concepts. Label learned totals as learned, not washes
completed. Show the specific reason for uncertain quota/readiness.

Use existing dashboard locations and registered appliance devices; optional
generated copies must not overwrite user dashboards. No new cloud service,
telemetry, token collection or AI request is required.

Keep routine diagnostic downloads allowlisted: health, coverage and aggregate
counts only. Raw timestamps, programmes, schedules, source IDs and request
records need a deliberately requested administrator export, not public issue
templates. Administrator-only reconciliation/reset must never start a device.

## Acceptance Gates

| Scenario | Expected result |
| --- | --- |
| Manufacturer software update causes a short power capture | No physical wash; pending wash preserved |
| Genuine wash has a rejected/missing-power learning capture | Operational evidence retained; learning unchanged |
| Duplicate Run/finish event, reload or retry/fallback | One physical cycle and one reservation, never two |
| Run followed by confirmed cancellation/fault | Separate outcome; no successful completion increment |
| Restart during Run or sent-but-unconfirmed command | Uncertainty remains; no invented completion or free retry |
| Manual start during automatic cooldown/exhausted quota | Manual action allowed subject to physical safety; automatic accounting stays honest |
| Recommendation changes to another programme or boundary passes | Revalidate requested programme at actual command time; block stale fit |
| Two concurrent requests | Serialized quota reservation; no oversubscription |
| Programme cannot be identified reliably | No guessed model/counter; affected finite allowance uncertain |
| More than ten cycles within one opportunity | Ledger covers full allowance without learning-history dependence |
| Adjacent zero/negative slots; positive gap; revised next day | Contiguous-window rules preserved, evidence never silently reset |
| DST/travel timezone change | Same UTC intervals, counts and physical outcomes |
| Write failure, corrupt/unknown-schema store, retention boundary | Preserve memory; fail closed for affected automatic commands |
| Downgrade and re-upgrade | Store preserved; rollback limitation explicit; no duplicate cycle |
| Rename appliance, edit policy, create custom dashboard | Identity, old learning and custom references unchanged |

Run unit/property-style boundary tests plus minimum-supported-HA persistence,
reload, security and controller acceptance with all commands mocked. Live
installation, restart and a supervised real cycle remain separately approved.

## Delivery Order

1. Agree accounting rules and completion evidence; resolve the PR #17 review.
2. Implement additive shadow ledger and recovery tests on a development branch.
3. Compare shadow outcomes with real observations without changing control.
4. Add opt-in enforcement and explanatory entities after parity evidence.
5. Agree beta/live acceptance, then separately approve stable publication.
6. Build guided appliance setup, followed by the programme-policy editor.

## Guided Setup Outline

Offer add/edit appliance forms alongside advanced YAML, not a forced migration.
Use entity selectors, stable IDs, read-only source review and explicit save.
Block edits during captures/queued work as today. A name change must not create
a new appliance; preserve unknown extension fields and unrelated policies.

Keep learning-source configuration separate from optional control activation.
Then offer exact learned-programme policy editing with independent normal and
negative permissions, clear zero-as-unlimited wording, and no new opt-ins.
Saving a policy never sends a physical command. Generalized control targets and
automatic dashboard creation remain separately scoped work.

Recommended removal semantics: stop observation/control only after idle/no
queue checks, retain memory by default, and require a separate explicit purge
to delete learned/operational history. Confirm this before implementing removal.

## Decisions Needed Before Runtime Implementation

1. Should confirmed manual/external cycles consume the subsequent automatic
   window allowance? Recommendation: yes, without blocking manual starts.
2. Should a physically started but failed/cancelled wash consume an allowance,
   while only successful finishes increment the completion counter?
   Recommendation: yes; otherwise repeated failures can bypass a finite cap.
3. Retain current overlap-based allowance counting, including both windows for
   a spanning wash, or change to start-window-only? Recommendation: retain it
   for the first version and label it clearly.
4. For appliance removal, keep learned/operational memory unless explicitly
   purged? Recommendation: yes, with independent stop and delete actions.
