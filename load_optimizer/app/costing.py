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
    for key in ("rates", "prices", "forecast", "all_rates"):
        rates = attributes.get(key)
        if isinstance(rates, list) and rates:
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


def recommend_cycle(
    models: list[dict],
    policies: list[dict],
    periods: list[dict],
    *,
    reference_utc: datetime,
    search_hours: int,
    candidate_interval_minutes: int,
) -> dict:
    """Find the least-cost policy-eligible program and start time."""
    policy_by_program = {policy["program"]: policy for policy in policies}
    candidates = []
    rejected_profiles = 0
    search_end = reference_utc + timedelta(hours=search_hours)
    first_start = _next_candidate(reference_utc, candidate_interval_minutes)
    for model in models:
        policy = policy_by_program.get(model["program"])
        if not policy or not policy["enabled"]:
            continue
        if not (policy["allow_normal_recommendation"] or policy["allow_negative_price_run"]):
            continue
        try:
            _profile_segments(model)
        except ValueError:
            rejected_profiles += 1
            continue
        start = first_start
        while start <= search_end:
            try:
                estimate = estimate_cycle_cost(start, model, periods)
            except ValueError:
                start += timedelta(minutes=candidate_interval_minutes)
                continue
            negative = estimate["energy_cost_pence"] < 0
            if policy["allow_normal_recommendation"] or (negative and policy["allow_negative_price_run"]):
                total_cost = estimate["energy_cost_pence"] + policy["estimated_overhead_cost_pence"]
                candidates.append({
                    "program": model["program"],
                    "start": start,
                    "energy_cost_pence": estimate["energy_cost_pence"],
                    "energy_kwh": estimate["energy_kwh"],
                    "cost_breakdown": estimate["cost_breakdown"],
                    "overhead_cost_pence": policy["estimated_overhead_cost_pence"],
                    "total_cost_pence": round(total_cost, 4),
                    "confidence": model.get("confidence", 0),
                    "preference_rank": policy["preference_rank"],
                    "negative_price_run": negative,
                })
            start += timedelta(minutes=candidate_interval_minutes)
    if not candidates:
        return {
            "status": "insufficient_profile" if rejected_profiles else "no_eligible_programs",
            "rejected_profiles": rejected_profiles,
        }
    cheapest = min(candidates, key=lambda item: (item["total_cost_pence"], item["preference_rank"]))
    selected_model = next(model for model in models if model["program"] == cheapest["program"])
    try:
        now_estimate = estimate_cycle_cost(reference_utc, selected_model, periods)
        policy = policy_by_program[cheapest["program"]]
        now_cost = round(now_estimate["energy_cost_pence"] + policy["estimated_overhead_cost_pence"], 4)
        now_breakdown = now_estimate["cost_breakdown"]
    except ValueError:
        now_cost = None
        now_breakdown = []
    return {
        "status": "ready",
        **cheapest,
        "cost_if_started_now_pence": now_cost,
        "cost_if_started_now_breakdown": now_breakdown,
        "potential_saving_pence": round(max(0.0, now_cost - cheapest["total_cost_pence"]), 4) if now_cost is not None else None,
        "candidate_count": len(candidates),
    }
