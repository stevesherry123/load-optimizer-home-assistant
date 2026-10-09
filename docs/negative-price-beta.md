# Automatic Free/Negative-Price Beta Acceptance

Version: `v1.7.0-beta.6`. Stable users remain on the existing stable release.
The owner approved this beta publication and installation on 9 October 2026;
stable promotion is a separate decision.

## Correction

Previously the planner rounded the first candidate forward to a five-minute
boundary, but automatic negative-price control required a start at or before
the scan time. Ordinary scans with seconds/microseconds could never satisfy
both conditions. Ranking all future opportunities together also deferred an
active opportunity when a later start had a better price.

The planner now evaluates an additional exact-scan-time candidate only for
negative-enabled programmes. Ready candidates precede future candidates in
both the negative recommendation and its programme-option list. Existing
programme priority and energy-per-minute ranking apply within those groups.
Normal scheduling retains its existing rounded candidate grid.

Only explicitly enabled Negative programmes can run. Per-programme/per-window
limits, negative-mode opt-in, the native-controller opt-in, request spacing,
deadlines, blocked periods, complete pricing coverage and physical safety
checks remain intact. Normal programme cooldowns do not prohibit opportunistic
runs; no selected policy value is changed by this beta.

## Verification

- Regression tests reproduce off-grid scan failures and future-price starvation.
- Negative and exactly zero-price periods work; positive prices do not become
  immediately eligible solely because a free period will occur later.
- Repeated runs remain eligible after completion despite a normal cooldown.
- Per-programme limits rotate selection to another Negative programme; separate
  opportunities have separate allowances and positive gaps do not trigger starts.
- Deadline, earliest-start, blocked-period, excluded-programme and high-power-fit
  checks cover the immediate candidate as well as the future search grid.
- A planner/controller test issues five isolated mock appliance starts across
  two opportunities, preserving normal-mode cooldowns and the closed-door state.
  It never selects the programme marked Negative: no and stops at configured caps.
- No learning/history schema, entity IDs, dashboard configuration or automatic
  control setting is migrated by this change.

Live installation must confirm the existing queued overnight request, learning,
entity identities, dashboard configuration, runtime and tariff history survive
one restart. Actual execution during a real negative-price window remains a
follow-up observation; isolated tests are not a claim that tomorrow's cycles
have already run.

Free Octoplus calendar events are not automatically overlaid or subscribed to.
The existing tariff sources or explicit special-price overlay must expose a
zero/negative price for the planner to use a promotional session.
