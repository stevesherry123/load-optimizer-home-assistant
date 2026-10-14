# Overnight Price Publication And Replanning

The 13 October wash exposed an automatic reservation made at 16:00 local time
before tomorrow's rates arrived. Quick65 remained queued for 22:05 even after
the full relevant night became priced. Replaying the published prices found a
cheaper overnight recommendation. This repair is in `v1.7.0-beta.7`, not stable.

## Behaviour

- Compare the whole current/next operational overnight window in the configured
  tariff timezone, including possible finishes of enabled normal programmes.
  A future finish deadline clips the required tail. Relevant contiguous prices
  matter, not a fixed publication time or all 48 slots of tomorrow.
- A short search horizon, gaps, conflicting overlapping rates or incomplete
  cycle tails prevent a new automatic overnight reservation. The scheduling
  explanation reports why it is waiting. A valid current recommendation alone
  is not enough to claim the whole night has been compared.
- Follow eligible, fully covered overnight recommendations while an automatic
  request is queued. Preserve its creation time and original overnight
  reservation. Record old/new programme, start and estimated cost on replanning.
- Stop replanning two minutes before the currently saved start, or as soon as
  execution begins. Never move a request into another overnight window.
- Explicit manual requests, including manual programme overrides, are never
  repriced into a different request. Running captures and command sequences
  are never interrupted. Existing permissions, confidence, cooldown and fresh
  physical/no-run source checks still apply.
- If a fresh recommendation is temporarily unavailable, retain a saved request.
  Do not invent prices or repeatedly consume overnight reservations. If no
  whole-night plan can be established, automatic planning waits rather than
  guessing; the user can still make an explicit manual request.

This is deterministic profile-based estimation, not a guarantee of actual cost
or a globally optimal plan for every appliance. The two-minute freeze bounds
late schedule churn; price changes inside that boundary do not replan the wash.
The existing command sequence may begin up to one minute before its saved time.

## Acceptance

Unit regressions cover partial publication, missing tails, gaps, duplicated and
conflicting periods, short horizons, finish deadlines, spring/autumn DST,
automatic-only replanning, unchanged reservations and manual/executing/frozen
requests. `ha_overnight_planning_smoke.py` runs the real minimum-HA coordinator
and registered entities against synthetic publication/revisions, checking exact
learning, identities and manual-request persistence without appliance commands.

Live installation/restart checks do not prove a future overnight wash ran.
Observe the next actual automatic request and completion before stable promotion.

## Live Installation, 14 October 2026

Published `v1.7.0-beta.7` from `46a06496a4f513670cc4ff8920b1901860d82169`
after all five GitHub checks passed, including 396 unit tests and real minimum-HA
acceptance. HACS downloaded that exact release. All appliance captures were idle,
mandatory sources ready and no request queued before one Home Assistant restart.

The recovered live runtime reports beta.7. Read-back preserved all 222 registered
entity identities, seven devices, both exact dashboard configurations, 18
learning/profile/policy entities, control opt-ins and tariff-history metadata.
All three learned-appliance cost states are ready; AI remains disabled.
Both entry diagnostics report successful updates and clean legacy cleanup; the
current in-memory system log contains no Load Optimizer errors. The retired
file-log endpoint was unavailable, so it was not treated as a clean log.

The live planner correctly waits for tomorrow's overnight prices before making
a reservation. An independent local replay of the recorded 13 October prices
confirms the partial feed is rejected and the later relevant overnight coverage
permits the cheaper Eco50 recommendation. Pre-run Quick65 means in that replay
were reconstructed from rounded published statistics; estimates are not bills.
No physical test wash, charger command, provider call or full backup was made.
Stable main, v1.5.7 and the upstream HACS submission are unchanged. The next real
automatic overnight/free-price execution remains an observation gate.
