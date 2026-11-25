# Free And Negative-Price Repeat Repairs

Status: unreleased development on `fix/negative-price-repeat-safety`,
13 October 2026, based on main `c16b9e9`. Selected scheduling logic from the
earlier `e6ba6ca` beta fix is reimplemented against the merged runtime-safety
repairs. Neither tariff-beta branch nor its version changes is included.

## Reproduced Problems

- An off-grid scan only considered the next five-minute candidate, so an
  otherwise usable free-price opportunity never became ready to start now.
- A cheaper or higher-priority future candidate could displace a usable current
  candidate and prevent repeat runs throughout the current opportunity.
- During the 30-minute automatic request interval, a new overnight request
  could occupy the queue even though the current negative opportunity remained
  usable. The explanation also reported overnight details for negative-only mode.
- When every programme reached its cap, the early no-candidate result omitted
  the negative-intent reason. Truncated learning history could undercount a cap.
- Final review reproduced malformed history claiming coverage by list length,
  out-of-order records claiming a pre-window anchor, and an overflowing runtime
  crashing the count. Shared cycle-span validation now rejects that evidence.

## Behaviour

The planner adds an exact-reference-time probe only for negative-enabled
programmes. It still requires a fully priced cycle, allowed start/finish bounds,
no full-cycle no-run overlap and a high-power profile section that fits one
contiguous free/negative window. Normal-only programmes retain their grid.

Executable current candidates take precedence over future candidates. Within
that group, existing programme priority, energy intensity, energy and cost
ordering are retained. This is an opportunity-driven repeat policy, not a
globally optimal whole-day packing algorithm or a promise of net profit.
Low-power cycle tails can still occur at positive prices; water/wear costs and
the explicit programme policy remain relevant.

Normal programme cooldowns are bypassed only for explicitly permitted negative
runs. The existing controller interval remains 30 minutes between automatic
negative requests, not a new wait after every finish. Running appliances,
already queued work, confidence, door/connectivity/remote activation and fresh
calendar/power preflight still apply. Existing requests are not preempted.
During a usable opportunity's retry wait, no new overnight reservation is made.

Before every automatic negative-price command and fallback, the preflight reads
the requested programme's current model, permission, cap, tariff sources and
manual special-price helpers. It reuses the planner at the actual current time
with no future search. Another programme's published fit cannot authorize or
veto that request. Missing/unavailable tariffs, conflicting overlaps, incomplete
whole-cycle coverage, changed schedule bounds and outgrown calendar coverage
block the start. Identical periods from multiple sources are deduplicated.
An unpublished next-day attribute is tolerated only when other live source data
fully covers this cycle. Explicit manual starts and normal-request pricing
behaviour are unchanged.

Finite caps retain their existing per-programme, per-contiguous-window meaning.
Adjacent negative and zero-price slots share one window; a positive-price gap
separates allowances. Counts come from learned cycles overlapping that window.
If the model has unretained older runs and no retained pre-window completion
establishes coverage, a finite cap pauses with `negative_run_history_incomplete`.
Malformed or out-of-order records cannot establish that coverage either. Runtime
values must be finite, positive, non-boolean and representable as an interval;
invalid evidence never rewrites the stored learning record.
An already reached cap retains `maximum_runs_per_window_reached`. Zero still
means deliberately unlimited; missing history does not invent a cap for it.

This does not create a durable physical-wash quota ledger. A manufacturer
update/rejected learning capture is not counted as a learned run. A separately
scoped ledger for confirmed physical completions, independent of learning
quality and retention, remains backlog work. Large finite allowances may pause
conservatively rather than reconstruct lost historical counts.

The automation explanation now reports the applicable negative programme,
confidence, wait reason and retry time, and readiness shows the retry warning.
Existing dashboard templates already consume these attributes; no new
dashboard, custom resource or production configuration is installed.

## Acceptance

- 322 unit tests pass, including off-grid execution, active/future ordering,
  programme flags, separate-window allowances, normal cooldown overrides,
  finite-history uncertainty, physical safety and queued-request preservation.
- The actual planner/controller simulation produces five confirmed mocked starts
  across two separate windows: Quick45, MachineCare, MachineCare, Quick45,
  MachineCare. NormalOnly never starts. Requests are at least 30 minutes apart;
  every simulated run passes fresh automatic preflight.
- `ha_negative_price_smoke.py` passes on Home Assistant 2024.12. It uses actual
  setup/options flows, registered entities, the compatibility runtime and native
  preflight. Synthetic learning completion rotates the programme; a changed
  no-run calendar and unavailable power veto it without another scan. Reload
  preserves exact learning, identities, opt-in state and the request interval.
- Existing imports, dashboard templates, onboarding, runtime safety, security
  and EV backend lifecycle checks pass. No new browser acceptance is claimed;
  the sandbox denied the EV runner's optional local HTTP listener.
- Follow-up review adds malformed/overflowing runtime, timezone, chronology and
  explicit-unlimited regressions. Bandit and working-tree/history credential
  scans pass; the history scan covers 245 commits before this follow-up commit.

## Resolved Command-Time Review Finding

The automatic preflight re-reads power and full-cycle no-run calendars, but does
not reprice the requested programme at the actual command time. The controller
instead consults the published negative recommendation's fit flag, without
checking that it still describes the requested programme. Power-on, selection
and fallback delays can age an otherwise valid high-power fit out of its window.
An isolated controller probe also accepted a stale MachineCare fit while the
requested programme was Quick45; no physical command was sent.

The approved follow-up now closes this execution-layer finding. Boundary tests
advance the clock through the 15-second power-on wait, 5-second selection wait,
and successive 20-second fallback waits. Each attempt rechecks the exact
programme; an overrun sends no subsequent start-capable command. Adapter tests
also cover revised/missing/conflicting prices, current permissions and caps,
helper overrides, deadline changes and model growth during calendar fetching.
The real minimum-HA smoke test vetoes revised prices, a different requested
programme's exhausted cap, and a delayed boundary without another scan.

These checks validate service-dispatch time against the learned profile. Remote
appliance/network latency and actual heating-phase variation can still shift
physical energy consumption; this is not a guarantee of supplier profit or an
instruction to stop an appliance already running. Physical-cycle accounting
remains separately designed work, not implemented by these repairs.

The new real-HA test runs in CI with all device commands intercepted and HTTP
listeners mocked. No supplier, AI provider or production HA request is needed.
Remote checks are recorded on the repository review request. Main merge,
release/version publication, production installation and supervised real-cycle
acceptance require separate approval. The HACS catalogue submission is untouched.
