"""Read-only, recent-cycle predictions; lifetime learning remains unchanged."""
from datetime import datetime
import math
from statistics import mean, pstdev

from .minute_profile import forecast, validate, option_snapshot

RECENT_RUNS = 5


def _positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def recent_prediction(model: dict) -> dict | None:
    """Use five dated, complete profiles, or retain the lifetime fallback."""
    eligible = []
    recent = model.get("recent_cycles", [])
    if not isinstance(recent, list):
        return None
    for cycle in recent:
        if not isinstance(cycle, dict) or cycle.get("learning_excluded") or cycle.get("exclusion_reason"):
            continue
        profile = cycle.get("normalised_power_profile_w")
        if not all(_positive(cycle.get(key)) for key in ("runtime_minutes", "energy_kwh")):
            continue
        if (not isinstance(profile, list) or len(profile) < 2
                or not all(type(p) in (int, float) and math.isfinite(p) and p >= 0 for p in profile)
                or not any(profile)):
            continue
        try:
            finish = datetime.fromisoformat(cycle["finish"])
            if finish.utcoffset() is None:
                continue
        except (ValueError, TypeError, KeyError):
            continue
        eligible.append((finish, cycle))
    eligible.sort(key=lambda item: item[0])
    if len(eligible) < RECENT_RUNS or len({stamp for stamp, _ in eligible}) != len(eligible):
        return None
    cycles = [cycle for _, cycle in eligible[-RECENT_RUNS:]]
    profiles = [cycle["normalised_power_profile_w"] for cycle in cycles]
    if len({len(profile) for profile in profiles}) != 1:
        return None
    runtimes = [cycle["runtime_minutes"] for cycle in cycles]
    energies = [cycle["energy_kwh"] for cycle in cycles]
    result = {
        "expected_runtime_minutes": round(mean(runtimes), 1),
        "runtime_stddev_minutes": round(pstdev(runtimes), 1),
        "expected_energy_kwh": round(mean(energies), 4),
        "energy_stddev_kwh": round(pstdev(energies), 4),
        "representative_profile_w": [round(mean(points), 3) for points in zip(*profiles)],
        "prediction_basis": "recent_five_completed_runs",
        "prediction_sample_count": RECENT_RUNS,
        "prediction_runtime_range_minutes": [min(runtimes), max(runtimes)],
        "prediction_energy_range_kwh": [min(energies), max(energies)],
    }

    profiles = [cycle.get("minute_energy_profile") for cycle in cycles]
    valid_profiles = [profile for profile in profiles if validate(profile)]
    result["minute_profile_sample_count"] = len(valid_profiles)
    result["power_profile_basis"] = "legacy_point_fallback"
    result["minute_profile_fallback_reason"] = "collecting_complete_minute_profiles"
    options = [option_snapshot(cycle.get("program_options")) for cycle in cycles]
    compatible = all(option == options[-1] for option in options)
    if len(valid_profiles) == RECENT_RUNS and compatible:
        profile = forecast(profiles, result["expected_runtime_minutes"] * 60, result["expected_energy_kwh"])
        if profile:
            result["minute_energy_profile"] = profile
            result["power_profile_basis"] = "minute_energy_v1"
            result["minute_profile_fallback_reason"] = None
    elif not compatible:
        result["minute_profile_fallback_reason"] = "programme_option_metadata_differs"
    result["program_options_status"] = options[-1].get("status", "not_exposed")
    return result
