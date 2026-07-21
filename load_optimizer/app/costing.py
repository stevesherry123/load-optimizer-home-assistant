"""Tariff normalization and read-only cycle cost estimation."""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FEED_ENTRY = re.compile(
    r"(?P<day>\d{1,2})/(?P<month>\d{1,2})\s+"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*=\s*"
    r"(?P<price>[+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*p",
    re.IGNORECASE,
)
STRUCTURED_RATE_KEYS = ("rates", "prices", "forecast", "all_rates")
SCHEDULE_STRATEGIES = {"cheapest_absolute", "cheapest_earliest_finish", "cheapest_latest_finish"}
WINDOW_PREFERENCES = {"any", "overnight_only", "daytime_only", "prefer_overnight", "prefer_daytime"}


def _nearest_year(day: int, month: int, reference_local: datetime) -> int:
    candidates = []
    for year in (reference_local.year - 1, reference_local.year, reference_local.year + 1):
        try:
            candidate = datetime(year, month, day)
        except ValueError:
            continue
        candidates.append((abs((candidate.date() - reference_local.date()).days), year))
    if not candidates:
        raise ValueError(f"Invalid tariff date: {day:02d}/{month:02d}")
    return min(candidates)[1]


def _utc_candidates(wall_time: datetime, local_timezone: ZoneInfo) -> list[datetime]:
    candidates = []
    for fold in (0, 1):
        aware = wall_time.replace(tzinfo=local_timezone, fold=fold)
        utc = aware.astimezone(timezone.utc)
        if utc.astimezone(local_timezone).replace(tzinfo=None) == wall_time and utc not in candidates:
            candidates.append(utc)
    return sorted(candidates)


def parse_ai_feed(
    feed: str,
    *,
    reference_utc: datetime,
    timezone_name: str = "Europe/London",
) -> list[dict]:
    """Convert the Octopus Intelligence ``ai_feed`` format into tariff periods."""
    if reference_utc.tzinfo is None or reference_utc.utcoffset() is None:
        raise ValueError("reference_utc must be timezone-aware")
    try:
        local_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"Unknown tariff timezone: {timezone_name}") from error
    reference_local = reference_utc.astimezone(local_timezone)
    occurrences: dict[datetime, int] = {}
    points = []
    for match in FEED_ENTRY.finditer(feed):
        values = match.groupdict()
        year = _nearest_year(int(values["day"]), int(values["month"]), reference_local)
        wall_time = datetime(
            year,
            int(values["month"]),
            int(values["day"]),
            int(values["hour"]),
            int(values["minute"]),
        )
        candidates = _utc_candidates(wall_time, local_timezone)
        occurrence = occurrences.get(wall_time, 0)
        occurrences[wall_time] = occurrence + 1
        if not candidates or occurrence >= len(candidates):
            raise ValueError(f"Invalid or duplicate tariff timestamp: {wall_time.isoformat()}")
        points.append((candidates[occurrence], float(values["price"])))
    if len(points) < 2:
        raise ValueError("Tariff feed must contain at least two price points")
    points.sort()
    if len({point[0] for point in points}) != len(points):
        raise ValueError("Tariff feed resolves to duplicate UTC timestamps")
    periods = []
    for index, (start, price) in enumerate(points):
        if index + 1 < len(points):
            end = points[index + 1][0]
        else:
            end = start + (points[-1][0] - points[-2][0])
        periods.append({"start": start, "end": end, "price_p_per_kwh": price})
    return periods


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Tariff timestamp must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Tariff timestamp must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _model_last_seen_utc(model: dict) -> datetime | None:
    """Return the latest known successful finish time for a learned program."""
    candidates = []
    for value in (model.get("last_seen"), model.get("last_updated")):
        try:
            candidates.append(_parse_timestamp(value))
        except (TypeError, ValueError):
            pass
    for cycle in model.get("recent_cycles", []) or []:
        try:
            candidates.append(_parse_timestamp(cycle.get("finish")))
        except (AttributeError, TypeError, ValueError):
            pass
    return max(candidates) if candidates else None


def _cooldown_until_utc(model: dict, policy: dict) -> datetime | None:
    hours = int(policy.get("minimum_hours_between_runs") or 0)
    if hours <= 0:
        return None
    last_seen = _model_last_seen_utc(model)
    if last_seen is None:
        return None
    return last_seen + timedelta(hours=hours)


def parse_structured_rates(rates: list[dict], *, price_unit: str) -> list[dict]:
    """Normalize common structured Home Assistant rate attributes."""
    periods = []
    for rate in rates:
        start_value = next((rate.get(key) for key in ("start", "start_time", "valid_from", "from") if rate.get(key)), None)
        end_value = next((rate.get(key) for key in ("end", "end_time", "valid_to", "to") if rate.get(key)), None)
        price_value = next((rate.get(key) for key in ("price_p_per_kwh", "price", "value_inc_vat", "value") if rate.get(key) is not None), None)
        if start_value is None or end_value is None or price_value is None:
            raise ValueError("Structured tariff rate is missing start, end, or price")
        price = float(price_value)
        if price_unit == "gbp_per_kwh":
            price *= 100
        periods.append({
            "start": _parse_timestamp(start_value),
            "end": _parse_timestamp(end_value),
            "price_p_per_kwh": round(price, 6),
        })
    periods.sort(key=lambda period: period["start"])
    return periods


def _find_structured_rates(value: object, *, depth: int = 0) -> list[dict] | None:
    """Find rate lists on direct attributes or nested Home Assistant event payloads."""
    if depth > 4:
        return None
    if isinstance(value, dict):
        for key in STRUCTURED_RATE_KEYS:
            rates = value.get(key)
            if isinstance(rates, list) and rates:
                return rates
        for nested_value in value.values():
            rates = _find_structured_rates(nested_value, depth=depth + 1)
            if rates:
                return rates
    return None


def tariff_periods_from_entity(
    entity: dict,
    *,
    reference_utc: datetime,
    timezone_name: str,
    price_unit: str,
) -> list[dict]:
    attributes = entity.get("attributes", {}) if entity else {}
    feed = attributes.get("ai_feed")
    if isinstance(feed, str) and feed.strip():
        return parse_ai_feed(feed, reference_utc=reference_utc, timezone_name=timezone_name)
    rates = _find_structured_rates(attributes)
    if rates:
        return parse_structured_rates(rates, price_unit=price_unit)
    raise ValueError("Tariff entity has no supported future-rate attribute")


def _profile_segments(model: dict) -> list[dict]:
    profile = model.get("representative_profile_w", [])
    runtime_minutes = model.get("expected_runtime_minutes")
    expected_energy = model.get("expected_energy_kwh")
    if len(profile) < 2 or not runtime_minutes or not expected_energy:
        raise ValueError("Program model has no costable power profile")
    duration_seconds = float(runtime_minutes) * 60
    segment_seconds = duration_seconds / (len(profile) - 1)
    unscaled_energy = sum(
        ((float(profile[index]) + float(profile[index + 1])) / 2) * segment_seconds / 3_600_000
        for index in range(len(profile) - 1)
    )
    if unscaled_energy <= 0:
        raise ValueError("Program profile contains no measurable energy")
    scale = float(expected_energy) / unscaled_energy
    return [
        {
            "offset_start": index * segment_seconds,
            "offset_end": (index + 1) * segment_seconds,
            "power_w": ((float(profile[index]) + float(profile[index + 1])) / 2) * scale,
        }
        for index in range(len(profile) - 1)
    ]


def estimate_cycle_cost(start: datetime, model: dict, periods: list[dict]) -> dict:
    """Overlay a scaled learned profile on tariff periods."""
    if start.tzinfo is None or start.utcoffset() is None:
        raise ValueError("Cycle start must be timezone-aware")
    start = start.astimezone(timezone.utc)
    cost = 0.0
    energy = 0.0
    breakdown_by_start: dict[datetime, dict] = {}
    for segment in _profile_segments(model):
        segment_start = start + timedelta(seconds=segment["offset_start"])
        segment_end = start + timedelta(seconds=segment["offset_end"])
        covered_seconds = 0.0
        for period in periods:
            overlap_start = max(segment_start, period["start"])
            overlap_end = min(segment_end, period["end"])
            if overlap_end <= overlap_start:
                continue
            seconds = (overlap_end - overlap_start).total_seconds()
            segment_energy = segment["power_w"] * seconds / 3_600_000
            segment_cost = segment_energy * period["price_p_per_kwh"]
            energy += segment_energy
            cost += segment_cost
            covered_seconds += seconds
            bucket = breakdown_by_start.setdefault(period["start"], {
                "start": period["start"],
                "end": period["end"],
                "price_p_per_kwh": period["price_p_per_kwh"],
                "energy_kwh": 0.0,
                "energy_cost_pence": 0.0,
            })
            bucket["energy_kwh"] += segment_energy
            bucket["energy_cost_pence"] += segment_cost
        if covered_seconds + 0.001 < (segment_end - segment_start).total_seconds():
            raise ValueError("Tariff does not fully cover the cycle")
    breakdown = [
        {
            "start": item["start"].isoformat(),
            "end": item["end"].isoformat(),
            "price_p_per_kwh": item["price_p_per_kwh"],
            "energy_kwh": round(item["energy_kwh"], 6),
            "energy_cost_pence": round(item["energy_cost_pence"], 4),
        }
        for item in sorted(breakdown_by_start.values(), key=lambda value: value["start"])
        if item["energy_kwh"] > 0
    ]
    return {
        "energy_kwh": round(energy, 6),
        "energy_cost_pence": round(cost, 4),
        "cost_breakdown": breakdown,
    }


def _next_candidate(reference: datetime, interval_minutes: int) -> datetime:
    reference = reference.astimezone(timezone.utc)
    seconds = interval_minutes * 60
    rounded = math.ceil(reference.timestamp() / seconds) * seconds
    return datetime.fromtimestamp(rounded, timezone.utc)


def parse_clock(value: str) -> tuple[int, int]:
    try:
        hour, minute = str(value).split(":", 1)
        hour = int(hour)
        minute = int(minute)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid clock time: {value}") from None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid clock time: {value}")
    return hour, minute


def in_time_window(value: datetime, start: str, end: str, timezone_name: str) -> bool:
    try:
        local_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"Unknown schedule timezone: {timezone_name}") from error
    local = value.astimezone(local_timezone)
    start_hour, start_minute = parse_clock(start)
    end_hour, end_minute = parse_clock(end)
    current_minutes = local.hour * 60 + local.minute
    start_minutes = start_hour * 60 + start_minute
    end_minutes = end_hour * 60 + end_minute
    if start_minutes == end_minutes:
        return True
    if start_minutes < end_minutes:
        return start_minutes <= current_minutes < end_minutes
    return current_minutes >= start_minutes or current_minutes < end_minutes


def candidate_window_score(candidate: dict, preference: str) -> int:
    if preference == "prefer_overnight":
        return 0 if candidate.get("is_overnight_start") else 1
    if preference == "prefer_daytime":
        return 0 if candidate.get("is_daytime_start") else 1
    return 0


def best_window_candidate(candidates: list[dict], *, overnight: bool) -> dict | None:
    matching = [
        candidate for candidate in candidates
        if bool(candidate.get("is_overnight_start")) is overnight
    ]
    if not matching:
        return None
    return min(matching, key=lambda item: (item["total_cost_pence"], item["preference_rank"], item["finish"]))


def candidate_green_overlap_seconds(candidate: dict, green_windows: list[dict]) -> float:
    """Return how many seconds of a candidate cycle overlap preferred green windows."""
    start = candidate.get("start")
    finish = candidate.get("finish")
    if not start or not finish or not green_windows:
        return 0.0
    overlap_seconds = 0.0
    for window in green_windows:
        window_start = window.get("start")
        window_end = window.get("end")
        if not window_start or not window_end:
            continue
        overlap_start = max(start, window_start)
        overlap_end = min(finish, window_end)
        if overlap_end > overlap_start:
            overlap_seconds += (overlap_end - overlap_start).total_seconds()
    return overlap_seconds


def annotate_green_context(candidate: dict, green_windows: list[dict]) -> dict:
    """Attach provider-neutral green-window context to a candidate."""
    overlap_seconds = candidate_green_overlap_seconds(candidate, green_windows)
    runtime_seconds = max(1.0, (candidate["finish"] - candidate["start"]).total_seconds())
    return {
        **candidate,
        "green_window_overlap_seconds": round(overlap_seconds),
        "green_window_overlap_percent": round((overlap_seconds / runtime_seconds) * 100, 2),
        "is_green_window_start": overlap_seconds > 0,
    }


def best_green_candidate(candidates: list[dict]) -> dict | None:
    """Choose the cheapest candidate that materially overlaps a green window."""
    matching = [candidate for candidate in candidates if candidate.get("green_window_overlap_seconds", 0) > 0]
    if not matching:
        return None
    return min(
        matching,
        key=lambda item: (
            item["total_cost_pence"],
            -item.get("green_window_overlap_seconds", 0),
            item["preference_rank"],
            item["finish"],
        ),
    )


def non_energy_cost_breakdown(policy: dict) -> dict:
    """Return configurable non-energy cycle costs for one program policy."""
    fixed_cost = float(policy.get("fixed_cost_pence", policy.get("estimated_overhead_cost_pence", 0)) or 0)
    water_litres = float(policy.get("water_litres", 0) or 0)
    water_cost_per_litre = float(policy.get("water_cost_pence_per_litre", 0) or 0)
    water_cost = water_litres * water_cost_per_litre
    wear_cost = float(policy.get("wear_cost_pence", 0) or 0)
    total = fixed_cost + water_cost + wear_cost
    return {
        "fixed_cost_pence": round(fixed_cost, 4),
        "water_litres": round(water_litres, 4),
        "water_cost_pence_per_litre": round(water_cost_per_litre, 6),
        "water_cost_pence": round(water_cost, 4),
        "wear_cost_pence": round(wear_cost, 4),
        "non_energy_cost_pence": round(total, 4),
    }


def apply_operating_costs(estimate: dict, policy: dict) -> dict:
    """Combine tariff energy cost with configurable per-cycle operating costs."""
    non_energy = non_energy_cost_breakdown(policy)
    energy_cost = float(estimate["energy_cost_pence"])
    total_cost = energy_cost + non_energy["non_energy_cost_pence"]
    return {
        **estimate,
        **non_energy,
        "energy_cost_pence": round(energy_cost, 4),
        "total_cost_pence": round(total_cost, 4),
        "operating_cost_breakdown": {
            "energy_cost_pence": round(energy_cost, 4),
            **non_energy,
            "total_cost_pence": round(total_cost, 4),
        },
    }


def summarize_window_candidate(candidate: dict | None, now_cost: float | None) -> dict | None:
    if not candidate:
        return None
    saving = None
    if now_cost is not None:
        saving = round(max(0.0, now_cost - candidate["total_cost_pence"]), 4)
    return {
        "program": candidate.get("program"),
        "start": candidate.get("start").isoformat() if candidate.get("start") else None,
        "finish": candidate.get("finish").isoformat() if candidate.get("finish") else None,
        "cost_pence": candidate.get("total_cost_pence"),
        "energy_cost_pence": candidate.get("energy_cost_pence"),
        "non_energy_cost_pence": candidate.get("non_energy_cost_pence"),
        "saving_vs_now_pence": saving,
        "energy_kwh": candidate.get("energy_kwh"),
        "confidence": candidate.get("confidence"),
        "green_window_overlap_seconds": candidate.get("green_window_overlap_seconds"),
        "green_window_overlap_percent": candidate.get("green_window_overlap_percent"),
        "is_green_window_start": candidate.get("is_green_window_start"),
    }


def summarize_decision(
    *,
    intent: str,
    candidate: dict | None,
    reference_utc: datetime,
    now_cost: float | None,
    ready_to_start: bool = False,
    reason: str | None = None,
) -> dict:
    if not candidate:
        return {
            "intent": intent,
            "status": "not_ready",
            "reason": reason or "no_candidate",
            "ready_to_start": False,
        }
    cost = candidate.get("total_cost_pence")
    saving = None
    if now_cost is not None and cost is not None:
        saving = round(max(0.0, now_cost - cost), 4)
    start = candidate.get("start")
    seconds_until_start = None
    if start:
        seconds_until_start = max(0, round((start - reference_utc).total_seconds()))
    return {
        "intent": intent,
        "status": "ready",
        "reason": reason,
        "ready_to_start": ready_to_start,
        "program": candidate.get("program"),
        "start": start.isoformat() if start else None,
        "finish": candidate.get("finish").isoformat() if candidate.get("finish") else None,
        "seconds_until_start": seconds_until_start,
        "cost_pence": cost,
        "energy_cost_pence": candidate.get("energy_cost_pence"),
        "non_energy_cost_pence": candidate.get("non_energy_cost_pence"),
        "saving_vs_now_pence": saving,
        "energy_kwh": candidate.get("energy_kwh"),
        "confidence": candidate.get("confidence"),
        "negative_price_run": candidate.get("negative_price_run"),
        "is_overnight_start": candidate.get("is_overnight_start"),
        "is_daytime_start": candidate.get("is_daytime_start"),
        "energy_kwh_per_minute": candidate.get("energy_kwh_per_minute"),
        "green_window_overlap_seconds": candidate.get("green_window_overlap_seconds"),
        "green_window_overlap_percent": candidate.get("green_window_overlap_percent"),
        "is_green_window_start": candidate.get("is_green_window_start"),
    }


def summarize_program_rotation(program_diagnostics: list[dict], limit: int = 10) -> dict:
    """Return a compact explanation of program availability and cooldown state."""
    excluded = []
    cooldowns = []
    for diagnostic in program_diagnostics:
        item = {
            "program": diagnostic.get("program"),
            "status": diagnostic.get("status"),
            "reason": diagnostic.get("reason"),
            "confidence": diagnostic.get("confidence"),
            "priced_points": diagnostic.get("priced_points", 0),
        }
        if diagnostic.get("cooldown_until"):
            item["cooldown_until"] = diagnostic["cooldown_until"]
            item["minimum_hours_between_runs"] = diagnostic.get("minimum_hours_between_runs")
        if diagnostic.get("status") != "included":
            excluded.append(item)
        if diagnostic.get("reason") == "cooldown_active" or diagnostic.get("rejected_cooldown_points", 0):
            cooldowns.append(item)
    return {
        "excluded_programs": excluded[:limit],
        "cooldown_programs": cooldowns[:limit],
    }


def summarize_alternative_programs(candidates: list[dict], selected: dict, limit: int = 8) -> list[dict]:
    """Summarise the cheapest visible option for each alternative program."""
    best_by_program = {}
    for candidate in candidates:
        program = candidate.get("program")
        if not program or program == selected.get("program"):
            continue
        previous = best_by_program.get(program)
        if previous is None or candidate["total_cost_pence"] < previous["total_cost_pence"]:
            best_by_program[program] = candidate
    alternatives = sorted(
        best_by_program.values(),
        key=lambda item: (item["total_cost_pence"], item.get("preference_rank", 50), item["finish"]),
    )
    return [
        {
            "program": item.get("program"),
            "start": item.get("start").isoformat() if item.get("start") else None,
            "finish": item.get("finish").isoformat() if item.get("finish") else None,
            "cost_pence": item.get("total_cost_pence"),
            "confidence": item.get("confidence"),
            "preference_rank": item.get("preference_rank"),
            "negative_price_run": item.get("negative_price_run"),
            "green_window_overlap_percent": item.get("green_window_overlap_percent"),
        }
        for item in alternatives[:limit]
    ]


def summarize_selection_policy(
    *,
    selected: dict,
    candidates: list[dict],
    comparison_candidates: list[dict],
    program_diagnostics: list[dict],
    schedule_strategy: str,
    window_preference: str,
    equivalent_cost_tolerance_pence: float,
    now_cost: float | None,
    best_overnight: dict | None,
    best_daytime: dict | None,
    greenest: dict | None,
    best_negative: dict | None,
    latest_allowed_finish: datetime | None,
) -> dict:
    rotation = summarize_program_rotation(program_diagnostics)
    selected_cost = selected.get("total_cost_pence")
    factors = [
        f"schedule_strategy:{schedule_strategy}",
        f"window_preference:{window_preference}",
    ]
    if equivalent_cost_tolerance_pence:
        factors.append(f"equivalent_cost_tolerance_pence:{equivalent_cost_tolerance_pence}")
    if latest_allowed_finish:
        factors.append("latest_finish_constraint_active")
    if rotation["cooldown_programs"]:
        factors.append("cooldown_rotation_active")
    if selected.get("negative_price_run"):
        factors.append("negative_price_candidate")
    if selected.get("green_window_overlap_seconds", 0) > 0:
        factors.append("green_window_overlap")

    def delta(candidate: dict | None) -> float | None:
        if not candidate or selected_cost is None or candidate.get("total_cost_pence") is None:
            return None
        return round(candidate["total_cost_pence"] - selected_cost, 4)

    return {
        "selected_program": selected.get("program"),
        "selected_start": selected.get("start").isoformat() if selected.get("start") else None,
        "selected_finish": selected.get("finish").isoformat() if selected.get("finish") else None,
        "selected_cost_pence": selected_cost,
        "selected_confidence": selected.get("confidence"),
        "selected_preference_rank": selected.get("preference_rank"),
        "selection_factors": factors,
        "eligible_program_count": len({item.get("program") for item in candidates}),
        "costed_program_count": len({item.get("program") for item in comparison_candidates}),
        "alternative_programs": summarize_alternative_programs(comparison_candidates, selected),
        "excluded_programs": rotation["excluded_programs"],
        "cooldown_programs": rotation["cooldown_programs"],
        "cost_if_started_now_pence": now_cost,
        "overnight_delta_pence": delta(best_overnight),
        "daytime_delta_pence": delta(best_daytime),
        "greenest_delta_pence": delta(greenest),
        "negative_price_program": best_negative.get("program") if best_negative else None,
    }


def summarize_forecast_candidates(candidates: list[dict], limit: int = 300) -> list[dict]:
    forecast = []
    for candidate in sorted(candidates, key=lambda item: (item["program"], item["start"]))[:limit]:
        forecast.append({
            "program": candidate.get("program"),
            "start": candidate.get("start").isoformat() if candidate.get("start") else None,
            "finish": candidate.get("finish").isoformat() if candidate.get("finish") else None,
            "cost_pence": candidate.get("total_cost_pence"),
            "energy_cost_pence": candidate.get("energy_cost_pence"),
            "non_energy_cost_pence": candidate.get("non_energy_cost_pence"),
            "energy_kwh": candidate.get("energy_kwh"),
            "confidence": candidate.get("confidence"),
            "is_overnight_start": candidate.get("is_overnight_start"),
            "is_daytime_start": candidate.get("is_daytime_start"),
            "green_window_overlap_seconds": candidate.get("green_window_overlap_seconds"),
            "green_window_overlap_percent": candidate.get("green_window_overlap_percent"),
            "is_green_window_start": candidate.get("is_green_window_start"),
        })
    return forecast


def forecast_cycle_costs(
    models: list[dict],
    policies: list[dict],
    periods: list[dict],
    *,
    reference_utc: datetime,
    forecast_hours: int,
    forecast_interval_minutes: int,
    overnight_start: str,
    overnight_end: str,
    schedule_timezone: str,
    forecast_limit: int,
    green_windows: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    policy_by_program = {policy["program"]: policy for policy in policies}
    forecast_end = reference_utc + timedelta(hours=max(0, forecast_hours))
    start_at = _next_candidate(reference_utc, forecast_interval_minutes)
    candidates = []
    diagnostics = []
    for model in models:
        diagnostic = {
            "program": model.get("program"),
            "status": "included",
            "reason": None,
            "candidate_points": 0,
            "priced_points": 0,
            "rejected_points": 0,
            "rejected_cooldown_points": 0,
            "runtime_minutes": model.get("expected_runtime_minutes"),
            "confidence": model.get("confidence"),
        }
        policy = policy_by_program.get(model["program"])
        if not policy or not policy["enabled"]:
            diagnostic.update(status="excluded", reason="policy_missing_or_disabled")
            diagnostics.append(diagnostic)
            continue
        if not (policy["allow_normal_recommendation"] or policy["allow_negative_price_run"]):
            diagnostic.update(status="excluded", reason="policy_not_allowed_for_recommendation")
            diagnostics.append(diagnostic)
            continue
        try:
            _profile_segments(model)
        except ValueError:
            diagnostic.update(status="excluded", reason="insufficient_profile")
            diagnostics.append(diagnostic)
            continue
        cooldown_until = _cooldown_until_utc(model, policy)
        if cooldown_until:
            diagnostic["cooldown_until"] = cooldown_until.isoformat()
            diagnostic["minimum_hours_between_runs"] = policy.get("minimum_hours_between_runs")
        start = start_at
        while start <= forecast_end:
            diagnostic["candidate_points"] += 1
            if cooldown_until and start < cooldown_until:
                diagnostic["rejected_cooldown_points"] += 1
                start += timedelta(minutes=forecast_interval_minutes)
                continue
            try:
                estimate = estimate_cycle_cost(start, model, periods)
            except ValueError:
                diagnostic["rejected_points"] += 1
                start += timedelta(minutes=forecast_interval_minutes)
                continue
            negative = estimate["energy_cost_pence"] < 0
            if policy["allow_normal_recommendation"] or (negative and policy["allow_negative_price_run"]):
                estimate = apply_operating_costs(estimate, policy)
                diagnostic["priced_points"] += 1
                is_overnight = in_time_window(start, overnight_start, overnight_end, schedule_timezone)
                candidate = {
                    "program": model["program"],
                    "start": start,
                    "finish": start + timedelta(minutes=float(model["expected_runtime_minutes"])),
                    "total_cost_pence": estimate["total_cost_pence"],
                    "energy_cost_pence": estimate["energy_cost_pence"],
                    "non_energy_cost_pence": estimate["non_energy_cost_pence"],
                    "energy_kwh": estimate["energy_kwh"],
                    "confidence": model.get("confidence", 0),
                    "is_overnight_start": is_overnight,
                    "is_daytime_start": not is_overnight,
                }
                candidates.append(annotate_green_context(candidate, green_windows or []))
            start += timedelta(minutes=forecast_interval_minutes)
        if diagnostic["priced_points"] == 0:
            reason = "cooldown_active" if diagnostic["rejected_cooldown_points"] else "no_fully_priced_forecast_points"
            diagnostic.update(status="excluded", reason=reason)
        diagnostics.append(diagnostic)
    return summarize_forecast_candidates(candidates, forecast_limit), diagnostics


def recommend_cycle(
    models: list[dict],
    policies: list[dict],
    periods: list[dict],
    *,
    reference_utc: datetime,
    search_hours: int,
    candidate_interval_minutes: int,
    schedule_strategy: str = "cheapest_absolute",
    equivalent_cost_tolerance_pence: float = 0.0,
    window_preference: str = "any",
    overnight_start: str = "20:00",
    overnight_end: str = "08:00",
    schedule_timezone: str = "Europe/London",
    earliest_start_utc: datetime | None = None,
    latest_finish_utc: datetime | None = None,
    forecast_hours: int = 12,
    forecast_interval_minutes: int = 30,
    forecast_limit: int = 300,
    green_windows: list[dict] | None = None,
) -> dict:
    """Find the least-cost policy-eligible program and start time."""
    if schedule_strategy not in SCHEDULE_STRATEGIES:
        raise ValueError(f"Unsupported schedule strategy: {schedule_strategy}")
    if window_preference not in WINDOW_PREFERENCES:
        raise ValueError(f"Unsupported window preference: {window_preference}")
    equivalent_cost_tolerance_pence = max(0.0, float(equivalent_cost_tolerance_pence))
    policy_by_program = {policy["program"]: policy for policy in policies}
    candidates = []
    comparison_candidates = []
    negative_candidates = []
    rejected_profiles = 0
    rejected_constraints = 0
    rejected_cooldowns = 0
    program_diagnostics = []
    search_end = reference_utc + timedelta(hours=search_hours)
    earliest_allowed_start = earliest_start_utc.astimezone(timezone.utc) if earliest_start_utc else reference_utc
    latest_allowed_finish = latest_finish_utc.astimezone(timezone.utc) if latest_finish_utc else None
    first_start = _next_candidate(max(reference_utc, earliest_allowed_start), candidate_interval_minutes)
    for model in models:
        diagnostic = {
            "program": model.get("program"),
            "status": "included",
            "reason": None,
            "candidate_points": 0,
            "priced_points": 0,
            "rejected_constraints": 0,
            "rejected_cooldown_points": 0,
            "rejected_unpriced_points": 0,
            "runtime_minutes": model.get("expected_runtime_minutes"),
            "confidence": model.get("confidence"),
        }
        policy = policy_by_program.get(model["program"])
        if not policy or not policy["enabled"]:
            diagnostic.update(status="excluded", reason="policy_missing_or_disabled")
            program_diagnostics.append(diagnostic)
            continue
        if not (policy["allow_normal_recommendation"] or policy["allow_negative_price_run"]):
            diagnostic.update(status="excluded", reason="policy_not_allowed_for_recommendation")
            program_diagnostics.append(diagnostic)
            continue
        try:
            _profile_segments(model)
        except ValueError:
            rejected_profiles += 1
            diagnostic.update(status="excluded", reason="insufficient_profile")
            program_diagnostics.append(diagnostic)
            continue
        cooldown_until = _cooldown_until_utc(model, policy)
        if cooldown_until:
            diagnostic["cooldown_until"] = cooldown_until.isoformat()
            diagnostic["minimum_hours_between_runs"] = policy.get("minimum_hours_between_runs")
        start = first_start
        while start <= search_end:
            diagnostic["candidate_points"] += 1
            finish = start + timedelta(minutes=float(model["expected_runtime_minutes"]))
            if latest_allowed_finish and finish > latest_allowed_finish:
                rejected_constraints += 1
                diagnostic["rejected_constraints"] += 1
                start += timedelta(minutes=candidate_interval_minutes)
                continue
            if cooldown_until and start < cooldown_until:
                rejected_cooldowns += 1
                diagnostic["rejected_cooldown_points"] += 1
                start += timedelta(minutes=candidate_interval_minutes)
                continue
            is_overnight = in_time_window(start, overnight_start, overnight_end, schedule_timezone)
            is_daytime = not is_overnight
            try:
                estimate = estimate_cycle_cost(start, model, periods)
            except ValueError:
                diagnostic["rejected_unpriced_points"] += 1
                start += timedelta(minutes=candidate_interval_minutes)
                continue
            negative = estimate["energy_cost_pence"] < 0
            if policy["allow_normal_recommendation"] or (negative and policy["allow_negative_price_run"]):
                estimate = apply_operating_costs(estimate, policy)
                diagnostic["priced_points"] += 1
                candidate = {
                    "program": model["program"],
                    "start": start,
                    "finish": finish,
                    "energy_cost_pence": estimate["energy_cost_pence"],
                    "energy_kwh": estimate["energy_kwh"],
                    "cost_breakdown": estimate["cost_breakdown"],
                    "overhead_cost_pence": estimate["fixed_cost_pence"],
                    "fixed_cost_pence": estimate["fixed_cost_pence"],
                    "water_litres": estimate["water_litres"],
                    "water_cost_pence_per_litre": estimate["water_cost_pence_per_litre"],
                    "water_cost_pence": estimate["water_cost_pence"],
                    "wear_cost_pence": estimate["wear_cost_pence"],
                    "non_energy_cost_pence": estimate["non_energy_cost_pence"],
                    "operating_cost_breakdown": estimate["operating_cost_breakdown"],
                    "total_cost_pence": estimate["total_cost_pence"],
                    "confidence": model.get("confidence", 0),
                    "preference_rank": policy["preference_rank"],
                    "negative_price_priority": policy.get("negative_price_priority", 50),
                    "negative_price_run": negative,
                    "energy_kwh_per_minute": round(estimate["energy_kwh"] / float(model["expected_runtime_minutes"]), 6),
                    "is_overnight_start": is_overnight,
                    "is_daytime_start": is_daytime,
                }
                candidate = annotate_green_context(candidate, green_windows or [])
                comparison_candidates.append(candidate)
                if negative and policy["allow_negative_price_run"]:
                    negative_candidates.append(candidate)
                if window_preference == "overnight_only" and not is_overnight:
                    start += timedelta(minutes=candidate_interval_minutes)
                    continue
                if window_preference == "daytime_only" and not is_daytime:
                    start += timedelta(minutes=candidate_interval_minutes)
                    continue
                candidates.append(candidate)
            start += timedelta(minutes=candidate_interval_minutes)
        if diagnostic["priced_points"] == 0:
            if diagnostic["rejected_cooldown_points"]:
                diagnostic.update(status="excluded", reason="cooldown_active")
            elif diagnostic["rejected_constraints"]:
                diagnostic.update(status="excluded", reason="outside_schedule_constraints")
            elif diagnostic["rejected_unpriced_points"]:
                diagnostic.update(status="excluded", reason="no_fully_priced_points")
            else:
                diagnostic.update(status="excluded", reason="no_eligible_candidates")
        program_diagnostics.append(diagnostic)
    if not candidates:
        return {
            "status": "insufficient_profile" if rejected_profiles else "no_eligible_programs",
            "rejected_profiles": rejected_profiles,
            "rejected_constraints": rejected_constraints,
            "rejected_cooldowns": rejected_cooldowns,
            "program_diagnostics": program_diagnostics,
            "earliest_allowed_start": earliest_allowed_start.isoformat() if earliest_allowed_start else None,
            "latest_allowed_finish": latest_allowed_finish.isoformat() if latest_allowed_finish else None,
        }
    cheapest_cost = min(item["total_cost_pence"] for item in candidates)
    equivalent_candidates = [
        item for item in candidates
        if item["total_cost_pence"] <= cheapest_cost + equivalent_cost_tolerance_pence
    ]
    if schedule_strategy == "cheapest_earliest_finish":
        cheapest = min(equivalent_candidates, key=lambda item: (candidate_window_score(item, window_preference), item["finish"], item["total_cost_pence"], item["preference_rank"]))
    elif schedule_strategy == "cheapest_latest_finish":
        cheapest = min(equivalent_candidates, key=lambda item: (candidate_window_score(item, window_preference), -item["finish"].timestamp(), item["total_cost_pence"], item["preference_rank"]))
    else:
        cheapest = min(candidates, key=lambda item: (item["total_cost_pence"], candidate_window_score(item, window_preference), item["preference_rank"], item["finish"]))
    selected_model = next(model for model in models if model["program"] == cheapest["program"])
    try:
        now_estimate = estimate_cycle_cost(reference_utc, selected_model, periods)
        policy = policy_by_program[cheapest["program"]]
        now_estimate = apply_operating_costs(now_estimate, policy)
        now_cost = now_estimate["total_cost_pence"]
        now_breakdown = now_estimate["cost_breakdown"]
        now_operating_breakdown = now_estimate["operating_cost_breakdown"]
    except ValueError:
        now_cost = None
        now_breakdown = []
        now_operating_breakdown = None
    best_overnight = best_window_candidate(comparison_candidates, overnight=True)
    best_daytime = best_window_candidate(comparison_candidates, overnight=False)
    greenest = best_green_candidate(comparison_candidates)
    immediate_candidate = min(
        comparison_candidates,
        key=lambda item: (abs((item["start"] - reference_utc).total_seconds()), item["total_cost_pence"], item["preference_rank"]),
    )
    soon_end = reference_utc + timedelta(hours=2)
    soon_candidates = [
        candidate for candidate in comparison_candidates
        if reference_utc <= candidate["start"] <= soon_end
    ]
    best_soon = min(
        soon_candidates,
        key=lambda item: (item["total_cost_pence"], item["preference_rank"], item["finish"]),
    ) if soon_candidates else None
    best_negative = max(
        negative_candidates,
        key=lambda item: (
            item["negative_price_priority"],
            item["energy_kwh_per_minute"],
            item["energy_kwh"],
            -item["total_cost_pence"],
            -item["preference_rank"],
        ),
    ) if negative_candidates else None
    cost_forecast, forecast_diagnostics = forecast_cycle_costs(
        models,
        policies,
        periods,
        reference_utc=reference_utc,
        forecast_hours=forecast_hours,
        forecast_interval_minutes=forecast_interval_minutes,
        overnight_start=overnight_start,
        overnight_end=overnight_end,
        schedule_timezone=schedule_timezone,
        forecast_limit=forecast_limit,
        green_windows=green_windows,
    )
    return {
        "status": "ready",
        **cheapest,
        "cost_if_started_now_pence": now_cost,
        "cost_if_started_now_breakdown": now_breakdown,
        "cost_if_started_now_operating_breakdown": now_operating_breakdown,
        "potential_saving_pence": round(max(0.0, now_cost - cheapest["total_cost_pence"]), 4) if now_cost is not None else None,
        "overnight_comparison": summarize_window_candidate(best_overnight, now_cost),
        "daytime_comparison": summarize_window_candidate(best_daytime, now_cost),
        "greenest_comparison": summarize_window_candidate(greenest, now_cost),
        "decision_policy": summarize_selection_policy(
            selected=cheapest,
            candidates=candidates,
            comparison_candidates=comparison_candidates,
            program_diagnostics=program_diagnostics,
            schedule_strategy=schedule_strategy,
            window_preference=window_preference,
            equivalent_cost_tolerance_pence=equivalent_cost_tolerance_pence,
            now_cost=now_cost,
            best_overnight=best_overnight,
            best_daytime=best_daytime,
            greenest=greenest,
            best_negative=best_negative,
            latest_allowed_finish=latest_allowed_finish,
        ),
        "green_window_candidate_count": len([
            candidate for candidate in comparison_candidates
            if candidate.get("green_window_overlap_seconds", 0) > 0
        ]),
        "green_window_count": len(green_windows or []),
        "now_recommendation": summarize_decision(
            intent="now",
            candidate=immediate_candidate,
            reference_utc=reference_utc,
            now_cost=now_cost,
            ready_to_start=True,
            reason="start_immediately",
        ),
        "soon_recommendation": summarize_decision(
            intent="soon",
            candidate=best_soon,
            reference_utc=reference_utc,
            now_cost=now_cost,
            ready_to_start=False,
            reason="best_within_2_hours",
        ),
        "overnight_recommendation": summarize_decision(
            intent="overnight",
            candidate=best_overnight,
            reference_utc=reference_utc,
            now_cost=now_cost,
            ready_to_start=False,
            reason="best_overnight",
        ),
        "negative_price_recommendation": summarize_decision(
            intent="negative_price",
            candidate=best_negative,
            reference_utc=reference_utc,
            now_cost=now_cost,
            ready_to_start=bool(best_negative and best_negative["start"] <= reference_utc),
            reason="best_negative_price_energy_intensity" if best_negative else "no_negative_price_candidate",
        ),
        "greenest_recommendation": summarize_decision(
            intent="greenest",
            candidate=greenest,
            reference_utc=reference_utc,
            now_cost=now_cost,
            ready_to_start=bool(greenest and greenest["start"] <= reference_utc),
            reason="best_green_window" if greenest else "no_green_window_candidate",
        ),
        "negative_price_candidate_count": len(negative_candidates),
        "cost_forecast": cost_forecast,
        "forecast_diagnostics": forecast_diagnostics,
        "forecast_hours": forecast_hours,
        "forecast_interval_minutes": forecast_interval_minutes,
        "candidate_count": len(candidates),
        "comparison_candidate_count": len(comparison_candidates),
        "rejected_constraints": rejected_constraints,
        "rejected_cooldowns": rejected_cooldowns,
        "program_diagnostics": program_diagnostics,
        "earliest_allowed_start": earliest_allowed_start.isoformat() if earliest_allowed_start else None,
        "latest_allowed_finish": latest_allowed_finish.isoformat() if latest_allowed_finish else None,
        "schedule_strategy": schedule_strategy,
        "equivalent_cost_tolerance_pence": equivalent_cost_tolerance_pence,
        "window_preference": window_preference,
        "overnight_start": overnight_start,
        "overnight_end": overnight_end,
        "schedule_timezone": schedule_timezone,
    }
