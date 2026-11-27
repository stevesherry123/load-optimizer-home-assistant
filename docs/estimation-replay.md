# Chronological estimation replay

`dev/replay_estimates.py` compares the existing lifetime mean with a fixed
five-run recent mean without changing learning, planning or devices. Supply a
private HA learning-store export and save the report outside tracked source:

```
python dev/replay_estimates.py /private/learning.json --instance 1 --output .local/estimate-replay.json
```

The report contains programme-level errors and sample counts, not raw household
traces. Treat even aggregate household results as private unless approved for
sharing. Input paths, credentials and raw traces must not enter public commits.

For each programme and measurement, reconstruct the older aggregate sum by
subtracting all retained runs from the lifetime total. For each retained holdout,
add back only preceding retained runs. The recent method uses only the preceding
five runs. Require at least five preceding retained runs; do not use the held-out
run or later runs in either prediction. Validate unique actual UTC finish times,
positive finite measurements and consistent aggregate counts. Incomplete input
is explicitly excluded, never filled with invented observations.

This is a small-sample diagnostic, not automatic calibration approval. Model
storage retains only ten recent cycles per programme. Options and independent
meter-counter deltas are not retained for every historical cycle; recorded energy
cannot therefore be treated as independently verified billed usage. The five-run
window is fixed before replay, not selected by optimising its holdout scores.

Next acceptance steps:

1. Preserve future pre-run estimates, programme options, full measured profile and
   meter-counter start/end values, including reset and source-gap diagnostics.
2. Compare recent-duration prediction prospectively with the unchanged estimator.
   Evaluate signed error, absolute error and deadline overruns across programmes.
3. Assess energy separately. Preserve total energy when increasing the costing
   profile's time resolution; test heating timing against actual tariff intervals.
4. Introduce a new model only after held-out and prospective evidence improves
   accuracy without weakening hard deadlines, tariff coverage or learning quality.
   Keep the old stored statistics and an explicit rollback path.

A successful wash verifies execution, not estimation accuracy. Never replace a
model with a percentage correction inferred from a single cycle.

## Runtime predictions from 1.9.0

The running totals and lifetime mean remain the historical record. The scheduling
prediction uses the five latest accepted completed cycles with distinct aware
finish timestamps, positive finite runtime/energy and compatible finite power
profiles. Insufficient, invalid or incompatible recent evidence falls back to the
lifetime model. Duration, energy and normalized power shape use the same cohort;
costing scales that shape to the predicted energy. Calendar coverage and running
finish estimates use that duration too. No stored learning data is rewritten.

Public programme summaries expose prediction_basis, prediction_sample_count,
lifetime_runtime_minutes and lifetime_energy_kwh. Recent predictions also expose
observed runtime and energy ranges and standard deviations. These describe the
sample, not a guarantee that a future run finishes inside its estimated bounds.
Confidence retains its existing lifetime consistency meaning. Programme options
are not available in the retained history, so the recent cohort cannot distinguish
option changes. Compare future quoted predictions with metered completed runs;
a good duration replay does not establish energy or price accuracy.

The replay command remains a historical baseline/candidate comparison; its raw
aggregate reconstruction does not call the updated runtime summary and does not
rewrite or calibrate the model. Keep prediction-time evidence for prospective
acceptance.

## Energy-preserving minute profiles from 1.10.0

Twenty interpolated point samples can miss an entire short heating burst. New
completed captures instead retain the integrated Wh of each elapsed minute,
including the actual duration of a partial final minute. They use the same
piecewise-linear integration as captured total energy. A minute bin is a
representation of available readings, not a claim of new one-minute sensor
measurements. Known missing readings, gaps over 180 seconds, invalid/duplicate
offsets, interrupted captures and inconsistent duration/energy do not qualify.
Captures over 24 hours retain the existing fallback.

Five compatible profiles from the same five completed runs used for duration and
energy are required. Their cumulative-energy curves are aligned to the predicted
duration and averaged. This small time resampling conserves energy instead of
resampling isolated power points; it is not a separate model of heating phases
and drying duration. Cost ranking, negative-window checks and minute forecast
charts use the same resulting profile. The recent energy estimate remains an
estimate and is not replaced by the latest counter value.

Raw counter deltas and capture start/finish timestamps are retained when available.
Explicit numeric/boolean Home Connect dishwasher option values exposed in the
programme source's program_options/options mapping are bounded and retained;
arbitrary source attributes, free text and entity mappings are not copied.
Absent option data is marked not_exposed, not guessed. Different observed option
metadata prevents profile promotion for that cohort. Unknown options cannot be
used to guarantee that historical settings match.

An upgrade can recover the one full raw last_cycle capture only when its exact
finish matches a unique retained programme record. It adds profile metadata,
never another learned run or a replacement lifetime statistic. Other historical
twenty-point profiles cannot recover the lost detail. The existing forecast
remains active during collection. Public programme attributes include
power_profile_basis, minute_profile_sample_count, minute_profile_fallback_reason
and a readable power_profile_summary. Normally one retained full capture is
available; four further compatible captures then complete the cohort.

Display charts aggregate bounded adjacent minute bins by energy, preserving the
displayed area; the cost engine retains all minute bins. Existing point formats
remain compatible (elapsed minutes in compact charts, progress percent in the
programme-model chart), with duplicate boundary points expressing steps.

Acceptance covers pulses between the old sample points, partial minutes, missing
data, no promotion of incompatible metadata, upgrade/reload preservation and a
second heater changing tariff cost/negative-window eligibility. Assess subsequent
real cycles using only their pre-run forecast. Do not count a current cycle's
compression reconstruction or a single earlier template as five-run acceptance.
