"""EV charging planner for Load Optimizer."""

from __future__ import annotations

import math
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UNKNOWN_STATES = {"", "unknown", "unavailable", "none", "None", None}


def state_float(entity: dict | None) -> float | None:
    """Extract a float from a Home Assistant state response."""
    if not entity or entity.get("state") in UNKNOWN_STATES:
        return None
    try:
        return float(entity.get("state"))
    except (TypeError, ValueError):
        return None


def connection_is_available(entity: dict | None) -> bool:
    """Return whether a connection status entity means the car can charge."""
    if not entity:
        return True
    state = str(entity.get("state") or "").strip().lower()
    if state in {"", "unknown", "unavailable"}:
        return False
    return state not in {"disconnected", "not_connected", "none", "idle_disconnected"}


def deadline_from_ready_by(
    ready_by: str | None,
    *,
    reference_utc: datetime,
    timezone_name: str,
) -> datetime | None:
    """Resolve a local HH:MM ready-by value to the next matching UTC datetime."""
    if not ready_by:
        return None
    try:
        hour, minute = [int(part) for part in str(ready_by).split(":", 1)]
        ready_time = time(hour=hour, minute=minute)
    except (TypeError, ValueError):
        return None
    try:
        local_tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        local_tz = timezone.utc
    local_now = reference_utc.astimezone(local_tz)
    candidate = datetime.combine(local_now.date(), ready_time, tzinfo=local_tz)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def plan_ev_charge(
    *,
    periods: list[dict],
    battery_percent: float | None,
    battery_capacity_kwh: float | None,
    charge_power_kw: float | None,
    target_percent: float = 100,
    charger_efficiency: float = 0.9,
    slot_minutes: int = 30,
    reference_utc: datetime | None = None,
    deadline_utc: datetime | None = None,
    connected: bool = True,
) -> dict:
    """Choose the cheapest upcoming charging slots for an EV."""
    reference_utc = (reference_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    validation_error = _validate_inputs(
        periods=periods,
        battery_percent=battery_percent,
        battery_capacity_kwh=battery_capacity_kwh,
        charge_power_kw=charge_power_kw,
        target_percent=target_percent,
        charger_efficiency=charger_efficiency,
        slot_minutes=slot_minutes,
        connected=connected,
    )
    if validation_error:
        return _not_ready(validation_error)

    assert battery_percent is not None
    assert battery_capacity_kwh is not None
    assert charge_power_kw is not None

    needed_battery_kwh = max(0.0, (target_percent - battery_percent) / 100 * battery_capacity_kwh)
    wall_energy_kwh = needed_battery_kwh / charger_efficiency
    if needed_battery_kwh <= 0:
        return {
            "status": "ready",
            "reason": "target_already_met",
            "ready_to_charge": False,
            "charge_now": False,
            "battery_percent": round(battery_percent, 3),
            "target_percent": round(target_percent, 3),
            "needed_battery_kwh": 0,
            "wall_energy_kwh": 0,
            "selected_slots": [],
            "estimated_cost_pence": 0,
            "estimated_profit_pence": 0,
        }

    slot_hours = slot_minutes / 60
    slot_energy_kwh = charge_power_kw * slot_hours
    slots_needed = math.ceil(wall_energy_kwh / slot_energy_kwh)
    candidate_slots = _candidate_slots(
        periods=periods,
        reference_utc=reference_utc,
        deadline_utc=deadline_utc,
        slot_minutes=slot_minutes,
        slot_energy_kwh=slot_energy_kwh,
    )
    selected = sorted(candidate_slots, key=lambda slot: (slot["price_p_per_kwh"], slot["start"]))[:slots_needed]
    selected.sort(key=lambda slot: slot["start"])
    ready = len(selected) >= slots_needed
    estimated_cost = sum(slot["cost_pence"] for slot in selected)
    charge_now = any(slot["start"] <= reference_utc < slot["end"] for slot in selected)

    return {
        "status": "ready" if ready else "not_ready",
        "reason": None if ready else "insufficient_tariff_coverage",
        "ready_to_charge": ready,
        "charge_now": ready and charge_now,
        "battery_percent": round(battery_percent, 3),
        "target_percent": round(target_percent, 3),
        "needed_battery_kwh": round(needed_battery_kwh, 4),
        "wall_energy_kwh": round(wall_energy_kwh, 4),
        "slot_energy_kwh": round(slot_energy_kwh, 4),
        "slots_needed": slots_needed,
        "slots_available": len(candidate_slots),
        "selected_slots": [_public_slot(slot) for slot in selected],
        "estimated_cost_pence": round(estimated_cost, 4),
        "estimated_profit_pence": round(abs(estimated_cost), 4) if estimated_cost < 0 else 0,
        "next_slot_start": selected[0]["start"].isoformat() if selected else None,
        "next_slot_end": selected[0]["end"].isoformat() if selected else None,
        "deadline": deadline_utc.isoformat() if deadline_utc else None,
    }


def _not_ready(reason: str) -> dict:
    return {
        "status": "not_ready",
        "reason": reason,
        "ready_to_charge": False,
        "charge_now": False,
        "selected_slots": [],
    }


def _validate_inputs(
    *,
    periods: list[dict],
    battery_percent: float | None,
    battery_capacity_kwh: float | None,
    charge_power_kw: float | None,
    target_percent: float,
    charger_efficiency: float,
    slot_minutes: int,
    connected: bool,
) -> str | None:
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
    if not 0 <= battery_percent <= 100:
        return "invalid_battery_percent"
    if not 0 < target_percent <= 100:
        return "invalid_target_percent"
    if battery_capacity_kwh <= 0:
        return "invalid_battery_capacity"
    if charge_power_kw <= 0:
        return "invalid_charge_power"
    if not 0 < charger_efficiency <= 1:
        return "invalid_charger_efficiency"
    if slot_minutes <= 0:
        return "invalid_slot_minutes"
    return None


def _candidate_slots(
    *,
    periods: list[dict],
    reference_utc: datetime,
    deadline_utc: datetime | None,
    slot_minutes: int,
    slot_energy_kwh: float,
) -> list[dict]:
    slots = []
    duration = timedelta(minutes=slot_minutes)
    for period in periods:
        period_start = period["start"].astimezone(timezone.utc)
        period_end = period["end"].astimezone(timezone.utc)
        cursor = max(_round_up(reference_utc, slot_minutes), period_start)
        cursor = _round_up(cursor, slot_minutes)
        while cursor + duration <= period_end:
            end = cursor + duration
            if deadline_utc and end > deadline_utc:
                break
            price = float(period["price_p_per_kwh"])
            slots.append({
                "start": cursor,
                "end": end,
                "price_p_per_kwh": price,
                "energy_kwh": slot_energy_kwh,
                "cost_pence": price * slot_energy_kwh,
            })
            cursor = end
    return slots


def _round_up(value: datetime, interval_minutes: int) -> datetime:
    value = value.astimezone(timezone.utc)
    interval_seconds = interval_minutes * 60
    timestamp = math.ceil(value.timestamp() / interval_seconds) * interval_seconds
    return datetime.fromtimestamp(timestamp, timezone.utc)


def _public_slot(slot: dict) -> dict:
    return {
        "start": slot["start"].isoformat(),
        "end": slot["end"].isoformat(),
        "price_p_per_kwh": slot["price_p_per_kwh"],
        "energy_kwh": round(slot["energy_kwh"], 4),
        "cost_pence": round(slot["cost_pence"], 4),
    }
