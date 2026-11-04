"""Advisory required and opportunistic EV charging plans."""

from __future__ import annotations

import math
import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UNKNOWN_STATES = {"", "unknown", "unavailable", "none", "None", None}
CHARGING_MODES = {"required", "opportunistic"}


def state_float(entity: dict | None) -> float | None:
    """Extract a finite numeric reading, preserving missing-data behaviour."""
    if not entity or entity.get("state") in UNKNOWN_STATES or isinstance(entity.get("state"), bool):
        return None
    try:
        value = float(entity.get("state"))
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def connection_is_available(entity: dict | None) -> bool:
    """Accept explicit connected states; an omitted advisory input is optional."""
    if not entity:
        return True
    return str(entity.get("state") or "").strip().lower() in {
        "connected", "on", "charging", "plugged_in",
    }


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def deadline_from_ready_by(
    ready_by: str | None, *, reference_utc: datetime, timezone_name: str,
) -> datetime | None:
    """Resolve the next local deadline, including repeated and skipped hours."""
    if not ready_by:
        return None
    if not isinstance(ready_by, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", ready_by):
        raise ValueError("Ready by must be a local HH:MM time")
    if not _aware(reference_utc):
        raise ValueError("Reference time must be timezone-aware")
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, TypeError, ValueError) as error:
        raise ValueError("Unknown deadline timezone") from error
    hour, minute = map(int, ready_by.split(":"))
    reference = reference_utc.astimezone(timezone.utc)
    local_now = reference.astimezone(zone)
    for day in (local_now.date(), local_now.date() + timedelta(days=1)):
        wall = datetime.combine(day, time(hour, minute))
        possible = {wall.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc) for fold in (0, 1)}
        valid = [candidate for candidate in possible
                 if candidate.astimezone(zone).replace(tzinfo=None) == wall]
        if not valid:
            # A skipped local time moves forward by the size of the clock jump.
            valid = [candidate for candidate in possible
                     if candidate.astimezone(zone).replace(tzinfo=None) > wall]
        future = [candidate for candidate in valid if candidate > reference]
        if future:
            return min(future)
    raise ValueError("Could not resolve the next local deadline")


def plan_ev_charge(
    *, periods: list[dict], battery_percent: float | None,
    battery_capacity_kwh: float | None, charge_power_kw: float | None,
    target_percent: float = 100, charger_efficiency: float = 0.9,
    slot_minutes: int = 30, reference_utc: datetime | None = None,
    deadline_utc: datetime | None = None, connected: bool = True,
    charging_mode: str = "required", maximum_price_p_per_kwh: float = 0,
) -> dict:
    """Select useful charging without operating a vehicle, charger or plug."""
    reference = reference_utc if reference_utc is not None else datetime.now(timezone.utc)
    if not _aware(reference) or deadline_utc is not None and not _aware(deadline_utc):
        return _not_ready("invalid_planning_time", charging_mode)
    reference = reference.astimezone(timezone.utc)
    deadline = deadline_utc.astimezone(timezone.utc) if deadline_utc else None
    error = _validate_inputs(
        periods=periods, battery_percent=battery_percent, battery_capacity_kwh=battery_capacity_kwh,
        charge_power_kw=charge_power_kw, target_percent=target_percent,
        charger_efficiency=charger_efficiency, slot_minutes=slot_minutes, connected=connected,
        charging_mode=charging_mode, maximum_price_p_per_kwh=maximum_price_p_per_kwh,
    )
    if error:
        return _not_ready(error, charging_mode)
    if deadline and deadline <= reference:
        return _not_ready("deadline_passed", charging_mode)
    try:
        periods = _checked_periods(periods)
    except (ValueError, TypeError, KeyError, OverflowError):
        return _not_ready("invalid_tariff_periods", charging_mode)

    needed_battery = max(0.0, (target_percent - battery_percent) / 100 * battery_capacity_kwh)
    needed_wall = needed_battery / charger_efficiency
    slot_energy = charge_power_kw * slot_minutes / 60
    candidates = _candidate_slots(
        periods=periods, reference_utc=reference, deadline_utc=deadline,
        slot_minutes=slot_minutes, slot_energy_kwh=slot_energy,
    ) if needed_battery > 0 else []
    eligible = [slot for slot in candidates if charging_mode == "required"
                or slot["price_p_per_kwh"] <= maximum_price_p_per_kwh]
    selected = []
    remaining = needed_wall
    for slot in sorted(eligible, key=lambda item: (item["price_p_per_kwh"], item["start"])):
        if remaining <= 0:
            break
        take = min(slot["energy_kwh"], remaining)
        end = min(slot["end"], slot["start"] + timedelta(hours=take / charge_power_kw))
        selected.append({**slot, "end": end, "energy_kwh": take,
                         "cost_pence": take * slot["price_p_per_kwh"]})
        remaining = max(0.0, remaining - take)
    selected.sort(key=lambda slot: slot["start"])
    planned_wall = math.fsum(slot["energy_kwh"] for slot in selected)
    planned_battery = min(needed_battery, planned_wall * charger_efficiency)
    shortfall = max(0.0, needed_battery - planned_battery)
    reachable = shortfall <= 1e-9
    estimated_cost = math.fsum(slot["cost_pence"] for slot in selected)
    has_plan = bool(selected)
    if needed_battery <= 0:
        status, reason = "ready", "target_already_met"
        summary = "The battery target is already met. No charging is planned."
    elif charging_mode == "opportunistic":
        status = "ready" if has_plan else "waiting"
        reason = None if has_plan else "no_slots_below_price_ceiling"
        summary = ("Charging is planned only at or below the price ceiling; reaching the target is not promised."
                   if has_plan else "Waiting for charging slots at or below the configured price ceiling.")
    elif reachable:
        status, reason = "ready", None
        summary = "The available charging plan is expected to reach the battery target."
    else:
        status = "partial" if has_plan else "not_ready"
        reason = "target_shortfall" if has_plan else "no_charging_slots_available"
        summary = ("Use the available charging slots; the battery is still expected to be below target."
                   if has_plan else "No usable charging slots are available before the deadline or planning horizon.")
    return {
        "status": status, "reason": reason, "summary": summary,
        "charging_mode": charging_mode, "advisory_only": True, "cost_basis": "electricity_only",
        "maximum_price_p_per_kwh": maximum_price_p_per_kwh if charging_mode == "opportunistic" else None,
        "ready_to_charge": has_plan,
        "charge_now": any(slot["start"] <= reference < slot["end"] for slot in selected),
        "target_reachable": reachable,
        "battery_percent": round(battery_percent, 3), "target_percent": round(target_percent, 3),
        "projected_battery_percent": round(battery_percent + planned_battery / battery_capacity_kwh * 100, 3),
        "needed_battery_kwh": round(needed_battery, 4), "wall_energy_kwh": round(needed_wall, 4),
        "planned_wall_energy_kwh": round(planned_wall, 4), "planned_battery_kwh": round(planned_battery, 4),
        "shortfall_battery_kwh": round(shortfall, 4), "slot_energy_kwh": round(slot_energy, 4),
        "slots_needed": math.ceil(needed_wall / slot_energy), "slots_available": len(eligible),
        "published_slots_available": len(candidates),
        "selected_slots": [_public_slot(slot) for slot in selected],
        "estimated_cost_pence": estimated_cost,
        "estimated_profit_pence": max(0.0, -estimated_cost),
        "estimated_electricity_credit_pence": max(0.0, -estimated_cost),
        "next_slot_start": selected[0]["start"].isoformat() if selected else None,
        "next_slot_end": selected[0]["end"].isoformat() if selected else None,
        "deadline": deadline.isoformat() if deadline else None,
    }


def _not_ready(reason: str, charging_mode: str = "required") -> dict:
    messages = {
        "vehicle_not_connected": "The vehicle is disconnected or its connection cannot be verified.",
        "no_tariff_periods": "Required electricity prices are unavailable.",
        "invalid_tariff_periods": "Electricity prices contain invalid or overlapping intervals.",
        "deadline_passed": "The supplied charging deadline has passed.",
        "invalid_planning_time": "The charging reference or deadline time could not be verified.",
    }
    return {"status": "not_ready", "reason": reason,
            "summary": messages.get(reason, "Charging inputs need review before a plan can be calculated."),
            "charging_mode": charging_mode, "advisory_only": True, "cost_basis": "electricity_only",
            "target_reachable": False, "ready_to_charge": False, "charge_now": False, "selected_slots": []}


def _validate_inputs(
    *, periods: list[dict], battery_percent: float | None, battery_capacity_kwh: float | None,
    charge_power_kw: float | None, target_percent: float, charger_efficiency: float,
    slot_minutes: int, connected: bool, charging_mode: str = "required",
    maximum_price_p_per_kwh: float = 0,
) -> str | None:
    if not isinstance(charging_mode, str) or charging_mode not in CHARGING_MODES:
        return "invalid_charging_mode"
    if not connected:
        return "vehicle_not_connected"
    if not periods:
        return "no_tariff_periods"
    if battery_percent is None:
        return "missing_battery_percent"
    if battery_capacity_kwh is None:
        return "missing_battery_capacity"
    if charge_power_kw is None:
        return "missing_charge_power"
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
           for value in (battery_percent, battery_capacity_kwh, charge_power_kw, target_percent,
                         charger_efficiency, slot_minutes, maximum_price_p_per_kwh)):
        return "invalid_charging_inputs"
    if not -1000 <= maximum_price_p_per_kwh <= 1000:
        return "invalid_price_ceiling"
    if not 0 <= battery_percent <= 100:
        return "invalid_battery_percent"
    if not 0 < target_percent <= 100:
        return "invalid_target_percent"
    if not 0 < battery_capacity_kwh <= 1000:
        return "invalid_battery_capacity"
    if not 0.1 <= charge_power_kw <= 1000:
        return "invalid_charge_power"
    if not 0.1 <= charger_efficiency <= 1:
        return "invalid_charger_efficiency"
    if not 1 <= slot_minutes <= 120 or int(slot_minutes) != slot_minutes:
        return "invalid_slot_minutes"
    return None


def _checked_periods(periods: list[dict]) -> list[dict]:
    unique = {}
    for period in periods:
        start, end, price = period["start"], period["end"], period["price_p_per_kwh"]
        if not _aware(start) or not _aware(end) or end <= start or isinstance(price, bool):
            raise ValueError("Invalid tariff interval")
        price = float(price)
        if not math.isfinite(price):
            raise ValueError("Invalid tariff price")
        start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
        unique[(start, end, price)] = {"start": start, "end": end, "price_p_per_kwh": price}
    ordered = sorted(unique.values(), key=lambda item: item["start"])
    if any(first["end"] > second["start"] for first, second in zip(ordered, ordered[1:])):
        raise ValueError("Overlapping tariff intervals")
    return ordered


def _candidate_slots(
    *, periods: list[dict], reference_utc: datetime, deadline_utc: datetime | None,
    slot_minutes: int, slot_energy_kwh: float,
) -> list[dict]:
    slots = []
    duration = timedelta(minutes=slot_minutes)
    power = slot_energy_kwh * 60 / slot_minutes
    horizon = min(reference_utc + timedelta(days=7), deadline_utc) if deadline_utc else reference_utc + timedelta(days=7)
    for period in periods:
        end_limit = min(period["end"], horizon)
        cursor = max(reference_utc, period["start"])
        while cursor < end_limit:
            grid = _round_up(cursor, slot_minutes)
            end = min(grid if grid > cursor else cursor + duration, end_limit)
            energy = power * (end - cursor).total_seconds() / 3600
            slots.append({"start": cursor, "end": end, "price_p_per_kwh": period["price_p_per_kwh"],
                          "energy_kwh": energy, "cost_pence": energy * period["price_p_per_kwh"]})
            cursor = end
    return slots


def _round_up(value: datetime, interval_minutes: int) -> datetime:
    interval = interval_minutes * 60
    return datetime.fromtimestamp(math.ceil(value.timestamp() / interval) * interval, timezone.utc)


def _public_slot(slot: dict) -> dict:
    return {"start": slot["start"].isoformat(), "end": slot["end"].isoformat(),
            "price_p_per_kwh": slot["price_p_per_kwh"], "energy_kwh": round(slot["energy_kwh"], 4),
            "cost_pence": round(slot["cost_pence"], 4)}
