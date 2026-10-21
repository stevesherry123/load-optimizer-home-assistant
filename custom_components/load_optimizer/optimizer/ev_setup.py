"""Read-only EV planning and setup checks, shared with the running coordinator."""

from __future__ import annotations

from datetime import datetime, timedelta
import math

from .ev_charging import connection_is_available, deadline_from_ready_by, plan_ev_charge, state_float
from .ev_monitor import measurement
from .tariffs import TariffDataUnavailable, tariff_periods_from_entity


def tariff_entities(config):
    result = []
    for key in ("tariff_entity", "tariff_entities"):
        value = config.get(key, "")
        values = value if isinstance(value, list) else str(value).split(",") if value is not None else []
        result.extend(str(item).strip() for item in values if str(item).strip())
    return list(dict.fromkeys(result))


def build_ev_plan(config, states, now):
    """Use the live tariff parser and planner, with no services or network calls."""
    periods = []
    tariff_error = None
    try:
        for entity_id in tariff_entities(config):
            source = states.get(entity_id)
            if not source or source["state"] in {"unknown", "unavailable"}:
                raise ValueError("Configured EV tariff source is unavailable")
            try:
                periods.extend(tariff_periods_from_entity(source, reference_utc=now,
                    timezone_name=config.get("tariff_timezone", "Europe/London"),
                    price_unit=config.get("tariff_price_unit", "p_per_kwh")))
            except TariffDataUnavailable:
                continue
        if not periods:
            raise ValueError("No configured EV tariff source contains future prices")
    except (TypeError, ValueError) as error:
        periods, tariff_error = [], str(error)
    target = state_float(states.get(config.get("target_percent_entity")))
    plan = plan_ev_charge(periods=periods,
        battery_percent=state_float(states.get(config.get("battery_entity"))),
        battery_capacity_kwh=state_float(states.get(config.get("battery_capacity_entity"))),
        charge_power_kw=float(config["charge_power_kw"]),
        target_percent=target if target is not None else float(config.get("target_percent", 100)),
        charger_efficiency=float(config.get("charger_efficiency", 0.9)),
        slot_minutes=int(config.get("slot_minutes", 30)), reference_utc=now,
        deadline_utc=deadline_from_ready_by(config.get("ready_by"), reference_utc=now,
            timezone_name=config.get("tariff_timezone", "Europe/London")),
        connected=connection_is_available(states.get(config.get("connection_status_entity"))))
    if tariff_error and plan.get("reason") == "no_tariff_periods":
        plan.update(reason="tariff_error", tariff_error=tariff_error)
    return plan, periods


def inspect_ev_setup(config, states, now):
    """Diagnose input readiness without claiming that physical charging is proven."""
    plan, periods = build_ev_plan(config, states, now)
    issues, warnings = [], []
    control = bool(config.get("ev_charger_switch"))
    roles = ["battery_entity", "battery_capacity_entity", "target_percent_entity", "connection_status_entity"]
    if control:
        roles += ["ev_charger_switch", "ev_charge_power_entity", "ev_charge_energy_entity", "ev_charging_status_entity"]
    for role in roles:
        entity_id = config.get(role)
        if not entity_id:
            if role in {"target_percent_entity", "connection_status_entity"} and (role != "connection_status_entity" or not control):
                continue
            issues.append(f"{role}: not configured")
            continue
        source = states.get(entity_id)
        if not source or source.get("state") in {None, "", "unknown", "unavailable"}:
            issues.append(f"{role}: missing or unavailable")
            continue
        unit = source.get("attributes", {}).get("unit_of_measurement")
        expected = {"battery_entity": "%", "battery_capacity_entity": "kWh", "target_percent_entity": "%"}.get(role)
        if expected and unit != expected:
            issues.append(f"{role}: expected unit {expected}")
        if expected:
            number = state_float(source)
            if (number is None or not math.isfinite(number)
                    or (expected == "%" and not 0 <= number <= 100)
                    or (role != "battery_entity" and number <= 0)):
                issues.append(f"{role}: invalid numeric reading")
        if role in {"ev_charge_power_entity", "ev_charge_energy_entity"}:
            if measurement(source, "power" if role == "ev_charge_power_entity" else "energy") is None:
                issues.append(f"{role}: invalid value or unsupported units")
        if role == "ev_charger_switch" and source["state"] != "off":
            issues.append("ev_charger_switch: must be off before enabling control")
        if role == "connection_status_entity" and control and source["state"].lower() not in {"connected", "charging", "plugged_in", "ready"}:
            issues.append("connection_status_entity: device is not confirmed connected")
        if role == "ev_charging_status_entity" and source["state"].lower() in {"error", "fault", "discharging"}:
            issues.append("ev_charging_status_entity: reports a fault")
        if role in {"battery_entity", "connection_status_entity", "ev_charge_power_entity", "ev_charge_energy_entity", "ev_charging_status_entity"}:
            try:
                age = (now - datetime.fromisoformat(source["last_reported"])).total_seconds()
                if not 0 <= age <= float(config.get("ev_telemetry_max_age_minutes", 15)) * 60:
                    raise ValueError
            except (KeyError, ValueError, TypeError):
                issues.append(f"{role}: feedback is stale or its age is unknown")
    limits = {}
    for key, default in (("ev_session_max_hours", 24), ("ev_session_max_energy_kwh", 120)):
        try:
            value = float(config.get(key, default))
            if not math.isfinite(value) or value <= 0:
                raise ValueError
            limits[key] = value
        except (ValueError, TypeError):
            issues.append(f"{key}: must be a positive finite number")
    if plan.get("status") != "ready":
        issues.append("charging plan: " + plan.get("reason", "not_ready"))
    if control and plan.get("wall_energy_kwh", 0) > limits.get("ev_session_max_energy_kwh", math.inf):
        warnings.append("The supply-energy allowance is smaller than the energy needed to reach the target.")
    hours = limits.get("ev_session_max_hours")
    if control and hours is not None and any(datetime.fromisoformat(slot["end"]) > now + timedelta(hours=hours)
                                            for slot in plan.get("selected_slots", [])):
        warnings.append("Selected charging extends beyond the session duration allowance, which includes waiting.")
    return {"plan": plan, "period_count": len(periods), "issues": issues, "warnings": warnings,
            "control_configured": control, "control_ready": control and not issues}
