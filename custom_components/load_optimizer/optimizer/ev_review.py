"""Bounded EV review data shared by native dashboards and isolated simulations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
from zoneinfo import ZoneInfo

try:
    from ..legacy.app_runtime import price_chart_data
except ImportError:  # Standalone, hardware-free development replay.
    from legacy.app_runtime import price_chart_data
from .ev_monitor import measurement


def review_snapshot(config, plan, periods, states, control, now):
    """Explain existing decisions; this function cannot issue a service call."""
    def number(key):
        state = states.get(config.get(key))
        try:
            value = float(state["state"]) if state else None
            return value if value is not None and math.isfinite(value) else None
        except (ValueError, TypeError):
            return None

    def source_value(key):
        state = states.get(config.get(key))
        return str(state.get("state", "unknown"))[:64] if state else "not_configured"

    def measured(key, quantity):
        state = states.get(config.get(key))
        return measurement(state, quantity) if state else None

    zone = config.get("tariff_timezone", "Europe/London")
    chart = price_chart_data(periods, now=now, timezone_name=zone)
    midnight = now.astimezone(ZoneInfo(zone)).replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = (midnight + timedelta(days=1)).astimezone(timezone.utc).timestamp() * 1000
    selected = plan.get("selected_slots", [])
    rows = []
    for slot in selected[:96]:
        rows.append({key: slot.get(key) for key in ("start", "end", "price_p_per_kwh", "energy_kwh", "cost_pence")})
        if len(json.dumps(rows)) > 10000:
            rows.pop()
            break
    sources = []
    for key in ("battery_entity", "battery_capacity_entity", "target_percent_entity", "connection_status_entity", "ev_charger_switch",
                "ev_charge_power_entity", "ev_charge_energy_entity", "ev_charging_status_entity"):
        entity_id = config.get(key)
        source = states.get(entity_id)
        age = None
        freshness_required = key not in {"battery_capacity_entity", "target_percent_entity", "ev_charger_switch"}
        status = "not_configured" if not entity_id else "missing"
        if source:
            status = "unavailable" if source.get("state") in {"unknown", "unavailable"} else "available"
            try:
                age = round((now - datetime.fromisoformat(source["last_reported"])).total_seconds())
                if freshness_required and (age < 0 or age > config.get("ev_telemetry_max_age_minutes", 15) * 60):
                    status = "stale" if status == "available" else status
            except (ValueError, TypeError, KeyError):
                if freshness_required and status == "available":
                    status = "age_unknown"
        sources.append({"role": key, "entity_id": entity_id, "status": status, "age_seconds": age,
                        "freshness_required": freshness_required})
    result = {
        "plan_status": plan.get("status", "not_ready"), "plan_reason": plan.get("reason"),
        "updated_at": now.isoformat(), "timezone": zone,
        "battery_percent": number("battery_entity"), "battery_capacity_kwh": number("battery_capacity_entity"),
        "target_percent": plan.get("target_percent", number("target_percent_entity") or config.get("target_percent", 100)),
        "charge_power_kw": config.get("charge_power_kw"), "charger_efficiency": config.get("charger_efficiency", 0.9),
        "needed_battery_kwh": plan.get("needed_battery_kwh"), "wall_energy_kwh": plan.get("wall_energy_kwh"),
        "estimated_cost_pence": plan.get("estimated_cost_pence"), "estimated_profit_pence": plan.get("estimated_profit_pence"),
        "selected_slots": rows, "selected_slot_count": len(selected), "selected_slots_truncated": len(rows) < len(selected),
        "planned_charging_minutes": round(sum((datetime.fromisoformat(slot["end"]) - datetime.fromisoformat(slot["start"])).total_seconds() / 60 for slot in selected), 1),
        "estimated_finish": selected[-1]["end"] if selected else None, "deadline": plan.get("deadline"),
        "charge_now": plan.get("charge_now", False),
        "charger_state": source_value("ev_charger_switch"), "charging_status": source_value("ev_charging_status_entity"),
        "actual_power_w": measured("ev_charge_power_entity", "power"),
        "meter_energy_kwh": measured("ev_charge_energy_entity", "energy"),
        "control": control or {"state": "advisory", "reason": "charger_control_not_configured", "delivery": {}},
        "sources": sources,
        "chart_horizon": "48h" if any(row[1] > tomorrow for row in chart["chart_price_periods"]) else "24h",
        **chart,
    }
    while len(json.dumps(result)) > 28000 and result["selected_slots"]:
        result["selected_slots"].pop()
        result["selected_slots_truncated"] = True
    return result
