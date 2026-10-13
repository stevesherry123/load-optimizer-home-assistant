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

Finite caps retain their existing per-programme, per-contiguous-window meaning.
Adjacent negative and zero-price slots share one window; a positive-price gap
separates allowances. Counts come from learned cycles overlapping that window.
If the model has unretained older runs and no retained pre-window completion
establishes coverage, a finite cap pauses with `negative_run_history_incomplete`.
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

- 306 unit tests pass, including off-grid execution, active/future ordering,
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

The new real-HA test runs in CI with all device commands intercepted and HTTP
listeners mocked. No supplier, AI provider or production HA request is needed.
Remote checks are recorded on the repository review request. Main merge,
release/version publication, production installation and supervised real-cycle
acceptance require separate approval. The HACS catalogue submission is untouched.
