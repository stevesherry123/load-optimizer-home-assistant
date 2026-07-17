"""Runtime entry point for the Load Optimizer Home Assistant App."""

from __future__ import annotations

import json
import logging
import math
import os
import signal
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from .costing import recommend_cycle, tariff_periods_from_entity
except ImportError:  # Running as /app/main.py in the Home Assistant container.
    from costing import recommend_cycle, tariff_periods_from_entity

APP_VERSION = "0.8.27"
API_BASE_URL = "http://supervisor/core/api"
DATA_PATH = Path("/data/load_optimizer.json")
OPTIONS_PATH = Path("/data/options.json")
STATUS_ENTITY = "sensor.load_optimizer_status"
RESTART_SAFETY_ENTITY = "sensor.load_optimizer_restart_safety"

PROGRAM_CLASSIFICATIONS = {
    "unclassified",
    "preferred",
    "alternative",
    "maintenance",
    "opportunistic",
    "disabled",
}

LOGGER = logging.getLogger("load_optimizer")
STOP_EVENT = threading.Event()


def configure_logging() -> None:
    level_name = os.getenv("LOAD_OPTIMIZER_LOG_LEVEL", "info").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [load_optimizer] %(message)s",
    )


def load_state(path: Path = DATA_PATH) -> dict:
    if not path.exists():
        return {"schema_version": 1, "instances": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        LOGGER.warning("Could not read persisted state: %s", error)
        return {"schema_version": 1, "instances": {}}


def save_state(data: dict, path: Path = DATA_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temporary_path.replace(path)


def load_options(path: Path = OPTIONS_PATH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def api_request(token: str, path: str, payload: dict | None = None) -> dict | None:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        f"{API_BASE_URL}{path}",
        data=data,
        method="POST" if payload is not None else "GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as error:
        LOGGER.warning("Home Assistant API request failed for %s: %s", path, error)
        return None


def render_template(token: str, template: str) -> object | None:
    response = api_request(token, "/template", {"template": template})
    if isinstance(response, str):
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return response
    return response


def publish_entity(token: str, entity_id: str, state: object, attributes: dict) -> None:
    api_request(token, f"/states/{entity_id}", {"state": str(state), "attributes": attributes})


def source_state(token: str, entity_id: str) -> dict | None:
    if not entity_id:
        return None
    return api_request(token, f"/states/{entity_id}")


def datetime_from_entity_state(entity_state: dict | None) -> datetime | None:
    if not entity_state:
        return None
    value = str(entity_state.get("state") or "").strip()
    if value in {"", "unknown", "unavailable", "none", "None"}:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def tariff_state_from_entity(token: str, entity_id: str) -> dict | None:
    state = source_state(token, entity_id)
    if state is None:
        return None
    attributes = state.setdefault("attributes", {})
    if any(isinstance(attributes.get(key), list) and attributes.get(key) for key in ("rates", "prices", "forecast", "all_rates")):
        return state
    for attribute in ("rates", "prices", "forecast", "all_rates"):
        template = "{{ state_attr('" + entity_id.replace("'", "\\'") + "', '" + attribute + "') | to_json }}"
        value = render_template(token, template)
        if isinstance(value, list) and value:
            attributes[attribute] = value
            attributes["tariff_rates_source"] = f"template_state_attr:{attribute}"
            break
    return state


def tariff_entity_diagnostic(state: dict | None) -> dict:
    if state is None:
        return {"readable": False}
    attributes = state.get("attributes", {})
    diagnostic = {
        "entity_id": state.get("entity_id"),
        "state": state.get("state"),
        "readable": True,
        "attribute_keys": sorted(attributes.keys()),
    }
    for key in ("rates", "prices", "forecast", "all_rates", "last_event_attributes"):
        value = attributes.get(key)
        if isinstance(value, list):
            diagnostic[f"{key}_type"] = "list"
            diagnostic[f"{key}_count"] = len(value)
        elif isinstance(value, dict):
            diagnostic[f"{key}_type"] = "dict"
            diagnostic[f"{key}_keys"] = sorted(value.keys())
        elif value is not None:
            diagnostic[f"{key}_type"] = type(value).__name__
    return diagnostic


def numeric_state(entity: dict | None) -> float | None:
    try:
        return float(entity["state"]) if entity else None
    except (KeyError, TypeError, ValueError):
        return None


def normalise_program(value: object) -> str:
    if value in (None, "", "unknown", "unavailable"):
        return "unknown"
    program = str(value)
    for prefix in (
        "Dishcare.Dishwasher.Program.",
        "BSH.Common.EnumType.Program.",
    ):
        if program.startswith(prefix):
            return program.removeprefix(prefix)
    return program


def profile_sample(start: datetime, now: datetime, power: float | None, energy: float | None) -> dict:
    sample = {
        "offset_seconds": max(0, round((now - start).total_seconds())),
        "power_w": round(power, 3) if power is not None else None,
    }
    if energy is not None:
        sample["energy_kwh"] = round(energy, 6)
    return sample


def normalise_profile(profile: list[dict], bins: int = 20) -> list[float]:
    points = sorted(
        (float(sample["offset_seconds"]), float(sample["power_w"]))
        for sample in profile
        if sample.get("power_w") is not None
    )
    if not points:
        return []
    if len(points) == 1:
        return [round(points[0][1], 3)] * bins

    duration = max(points[-1][0], 1.0)
    result = []
    right = 1
    for index in range(bins):
        target = duration * index / (bins - 1)
        while right < len(points) - 1 and points[right][0] < target:
            right += 1
        left_time, left_power = points[right - 1]
        right_time, right_power = points[right]
        if right_time == left_time:
            value = right_power
        else:
            ratio = (target - left_time) / (right_time - left_time)
            value = left_power + ratio * (right_power - left_power)
        result.append(round(value, 3))
    return result


def profile_energy_kwh(profile: list[dict]) -> float | None:
    points = sorted(
        (float(sample["offset_seconds"]), float(sample["power_w"]))
        for sample in profile
        if sample.get("offset_seconds") is not None and sample.get("power_w") is not None
    )
    if len(points) < 2:
        return None
    energy = 0.0
    for (start_seconds, start_power), (end_seconds, end_power) in zip(points, points[1:]):
        duration_seconds = end_seconds - start_seconds
        if duration_seconds <= 0:
            continue
        energy += ((start_power + end_power) / 2) * duration_seconds / 3_600_000
    return round(energy, 4)


def update_running_stat(model: dict, name: str, value: float | None) -> None:
    if value is None:
        return
    stat = model.setdefault("statistics", {}).setdefault(name, {"count": 0, "mean": 0.0, "m2": 0.0})
    stat["count"] += 1
    delta = float(value) - stat["mean"]
    stat["mean"] += delta / stat["count"]
    stat["m2"] += delta * (float(value) - stat["mean"])


def stat_summary(model: dict, name: str, digits: int) -> tuple[float | None, float | None]:
    stat = model.get("statistics", {}).get(name)
    if not stat or not stat["count"]:
        return None, None
    variance = stat["m2"] / (stat["count"] - 1) if stat["count"] > 1 else 0.0
    return round(stat["mean"], digits), round(math.sqrt(max(0.0, variance)), digits)


def cycle_quality_issue(config: dict, cycle: dict) -> str | None:
    min_runtime = float(config.get("learning_min_runtime_minutes", 5))
    min_samples = int(config.get("learning_min_samples", 3))
    min_energy = float(config.get("learning_min_energy_kwh", 0.001))
    runtime = cycle.get("runtime_minutes")
    samples = cycle.get("sample_count")
    energy = cycle.get("energy_kwh")
    if runtime is not None and float(runtime) < min_runtime:
        return f"runtime_below_{min_runtime:g}_minutes"
    if samples is not None and int(samples) < min_samples:
        return f"samples_below_{min_samples}"
    if energy is not None and float(energy) < min_energy:
        return f"energy_below_{min_energy:g}_kwh"
    return None


def rebuild_model_from_recent_cycles(model: dict, valid_cycles: list[dict]) -> None:
    existing_profile = model.get("representative_profile_w", [])
    valid_profiles = [
        cycle["normalised_power_profile_w"]
        for cycle in valid_cycles
        if isinstance(cycle.get("normalised_power_profile_w"), list)
        and len(cycle.get("normalised_power_profile_w", [])) >= 2
    ]
    model.clear()
    model["runs"] = 0
    model["recent_cycles"] = []
    if existing_profile:
        model["representative_profile_cleared_reason"] = "quality_repair_removed_suspicious_cycles"
    for cycle in valid_cycles:
        model["runs"] += 1
        finish = cycle.get("finish")
        if finish and not model.get("first_seen"):
            model["first_seen"] = finish
        if finish:
            model["last_seen"] = finish
            model["last_updated"] = finish
        update_running_stat(model, "runtime_minutes", cycle.get("runtime_minutes"))
        update_running_stat(model, "energy_kwh", cycle.get("energy_kwh"))
        update_running_stat(model, "peak_power_w", cycle.get("peak_power_w"))
        model.setdefault("recent_cycles", []).append(cycle)
    del model["recent_cycles"][:-10]
    if valid_profiles:
        profile_count = len(valid_profiles)
        model["representative_profile_w"] = [
            round(sum(profile[index] for profile in valid_profiles) / profile_count, 3)
            for index in range(len(valid_profiles[0]))
        ]
        model["profile_count"] = profile_count
    else:
        model["representative_profile_w"] = existing_profile
        model["profile_count"] = 1 if len(existing_profile) >= 2 else 0


def repair_missing_profile_from_last_cycle(instance: dict) -> None:
    last = instance.get("last_cycle", {})
    program = normalise_program(last.get("program"))
    if program == "unknown":
        return
    model = instance.get("program_models", {}).get(program)
    if not model or len(model.get("representative_profile_w", [])) >= 2:
        return
    profile = normalise_profile(last.get("power_profile", []))
    if len(profile) < 2:
        return
    model["representative_profile_w"] = profile
    model["profile_count"] = max(1, int(model.get("profile_count", 0)))
    model["representative_profile_repaired_from"] = "last_cycle_power_profile"


def repair_learning_quality(database: dict, configs: list[dict]) -> None:
    config_by_id = {str(config["instance_id"]): config for config in configs}
    for instance_id, instance in database.get("instances", {}).items():
        config = config_by_id.get(str(instance_id))
        if not config:
            continue
        excluded = None
        repaired = False
        for program, model in list(instance.get("program_models", {}).items()):
            recent_cycles = model.get("recent_cycles", [])
            if not recent_cycles:
                continue
            valid_cycles = []
            removed_cycles = []
            for cycle in recent_cycles:
                reason = cycle_quality_issue(config, cycle)
                if reason:
                    removed = dict(cycle)
                    removed.update({
                        "program": program,
                        "learning_excluded": True,
                        "exclusion_reason": reason,
                    })
                    removed_cycles.append(removed)
                else:
                    valid_cycles.append(cycle)
            if not removed_cycles:
                continue
            repaired = True
            excluded = instance.setdefault("quality_excluded_cycles", [])
            excluded.extend(removed_cycles)
            instance["last_discarded_cycle"] = removed_cycles[-1]
            if valid_cycles:
                rebuild_model_from_recent_cycles(model, valid_cycles)
            else:
                instance["program_models"].pop(program, None)
        if repaired:
            del instance["quality_excluded_cycles"][:-20]
            instance["runs"] = sum(
                int(model.get("runs", 0))
                for model in instance.get("program_models", {}).values()
            )
        repair_missing_profile_from_last_cycle(instance)


def program_summary(program: str, model: dict) -> dict:
    runtime, runtime_stddev = stat_summary(model, "runtime_minutes", 1)
    energy, energy_stddev = stat_summary(model, "energy_kwh", 4)
    peak, _ = stat_summary(model, "peak_power_w", 1)
    variations = []
    if runtime and runtime_stddev is not None:
        variations.append(runtime_stddev / runtime)
    if energy and energy_stddev is not None:
        variations.append(energy_stddev / energy)
    consistency = max(0.0, 1.0 - min(max(variations, default=0.0), 1.0))
    confidence = round(100 * min(model.get("runs", 0) / 5, 1.0) * consistency)
    return {
        "program": program,
        "runs": model.get("runs", 0),
        "first_seen": model.get("first_seen"),
        "last_seen": model.get("last_seen") or model.get("last_updated"),
        "profile_count": model.get("profile_count", 0),
        "expected_runtime_minutes": runtime,
        "runtime_stddev_minutes": runtime_stddev,
        "expected_energy_kwh": energy,
        "energy_stddev_kwh": energy_stddev,
        "average_peak_power_w": peak,
        "confidence": confidence,
        "representative_profile_w": model.get("representative_profile_w", []),
        "recent_cycles": model.get("recent_cycles", []),
    }


def compact_profile_data(models: dict, last_cycle: dict) -> dict:
    """Build a small chart-friendly profile payload for dashboard cards."""
    program_profiles = []
    for program, model in sorted(models.items()):
        summary = program_summary(program, model)
        profile = summary.get("representative_profile_w") or []
        runtime = summary.get("expected_runtime_minutes")
        if len(profile) < 2 or not runtime:
            continue
        denominator = max(len(profile) - 1, 1)
        points = [
            [
                round(index * float(runtime) / denominator, 3),
                round(float(power), 3),
            ]
            for index, power in enumerate(profile)
            if power is not None
        ]
        program_profiles.append({
            "program": program,
            "runs": summary.get("runs", 0),
            "runtime_minutes": runtime,
            "energy_kwh": summary.get("expected_energy_kwh"),
            "confidence": summary.get("confidence", 0),
            "profile_count": summary.get("profile_count", 0),
            "points": points,
        })

    last_profile = last_cycle.get("power_profile") or []
    last_cycle_points = [
        [
            round(float(sample.get("offset_seconds", 0)) / 60, 3),
            round(float(sample["power_w"]), 3),
        ]
        for sample in last_profile
        if sample.get("power_w") is not None
    ]

    return {
        "point_format": ["offset_minutes", "power_w"],
        "program_profiles": program_profiles,
        "last_cycle": {
            "program": normalise_program(last_cycle.get("program")),
            "runtime_minutes": last_cycle.get("runtime_minutes"),
            "energy_kwh": last_cycle.get("energy_kwh"),
            "sample_count": len(last_cycle_points),
            "points": last_cycle_points,
        },
    }


def update_program_model(instance: dict, cycle: dict) -> dict:
    program = normalise_program(cycle.get("program"))
    if program == "unknown":
        program = "Default"
    model = instance.setdefault("program_models", {}).setdefault(program, {"runs": 0})
    model["runs"] += 1
    if not model.get("first_seen"):
        model["first_seen"] = cycle.get("finish")
    model["last_seen"] = cycle.get("finish")
    update_running_stat(model, "runtime_minutes", cycle.get("runtime_minutes"))
    update_running_stat(model, "energy_kwh", cycle.get("energy_kwh"))
    update_running_stat(model, "peak_power_w", cycle.get("peak_power"))

    profile = normalise_profile(cycle.get("power_profile", []))
    if profile:
        profile_count = int(model.get("profile_count", 0)) + 1
        previous = model.get("representative_profile_w", [0.0] * len(profile))
        model["representative_profile_w"] = [
            round(old + (new - old) / profile_count, 3)
            for old, new in zip(previous, profile)
        ]
        model["profile_count"] = profile_count
    model["last_updated"] = cycle.get("finish")
    recent_cycles = model.setdefault("recent_cycles", [])
    recent_cycles.append({
        "finish": cycle.get("finish"),
        "runtime_minutes": cycle.get("runtime_minutes"),
        "energy_kwh": cycle.get("energy_kwh"),
        "peak_power_w": cycle.get("peak_power"),
        "sample_count": cycle.get("sample_count"),
        "energy_source": cycle.get("energy_source"),
        "normalised_power_profile_w": profile,
    })
    del recent_cycles[:-10]
    return program_summary(program, model)


def bootstrap_program_models(database: dict) -> None:
    for instance in database.get("instances", {}).values():
        if "program_models" not in instance and instance.get("last_cycle"):
            update_program_model(instance, instance["last_cycle"])


def default_program_policy(program: str) -> dict:
    return {
        "program": program,
        "configured": False,
        "classification": "unclassified",
        "enabled": True,
        "preference_rank": 50,
        "allow_normal_recommendation": False,
        "allow_negative_price_run": False,
        "minimum_days_between_runs": 0,
        "minimum_hours_between_runs": 0,
        "maximum_runs_per_window": 0,
        "negative_price_priority": 50,
        "estimated_overhead_cost_pence": 0.0,
    }


def normalise_program_policy(raw: dict) -> dict:
    program = normalise_program(raw.get("program"))
    if program == "unknown":
        raise ValueError("Program policy requires a program name")
    policy = default_program_policy(program)
    classification = str(raw.get("classification", "unclassified")).lower()
    if classification not in PROGRAM_CLASSIFICATIONS:
        raise ValueError(f"Unsupported program classification: {classification}")
    policy.update({
        "configured": True,
        "classification": classification,
        "enabled": bool(raw.get("enabled", policy["enabled"])),
        "preference_rank": max(1, min(100, int(raw.get("preference_rank", policy["preference_rank"])))),
        "allow_normal_recommendation": bool(raw.get("allow_normal_recommendation", policy["allow_normal_recommendation"])),
        "allow_negative_price_run": bool(raw.get("allow_negative_price_run", policy["allow_negative_price_run"])),
        "minimum_days_between_runs": max(0, int(raw.get("minimum_days_between_runs", policy["minimum_days_between_runs"]))),
        "minimum_hours_between_runs": max(0, int(raw.get(
            "minimum_hours_between_runs",
            int(raw.get("minimum_days_between_runs", policy["minimum_days_between_runs"])) * 24
        ))),
        "maximum_runs_per_window": max(0, int(raw.get("maximum_runs_per_window", policy["maximum_runs_per_window"]))),
        "negative_price_priority": max(1, min(100, int(raw.get("negative_price_priority", policy["negative_price_priority"])))),
        "estimated_overhead_cost_pence": max(0.0, float(raw.get("estimated_overhead_cost_pence", policy["estimated_overhead_cost_pence"]))),
    })
    if classification == "disabled":
        policy.update(enabled=False, allow_normal_recommendation=False, allow_negative_price_run=False)
    return policy


def resolve_program_policies(models: dict, configured: list[dict]) -> list[dict]:
    resolved = {program: default_program_policy(program) for program in models}
    for raw in configured:
        try:
            policy = normalise_program_policy(raw)
        except (TypeError, ValueError) as error:
            LOGGER.warning("Ignoring invalid program policy: %s", error)
            continue
        resolved[policy["program"]] = policy
    return [resolved[program] for program in sorted(resolved)]


def program_catalogue(models: dict, policies: list[dict]) -> list[dict]:
    model_programs = set(models)
    policy_by_program = {policy["program"]: policy for policy in policies}
    catalogue = []
    for program in sorted(model_programs | set(policy_by_program)):
        summary = program_summary(program, models[program]) if program in models else {
            "program": program,
            "runs": 0,
            "profile_count": 0,
            "expected_runtime_minutes": None,
            "expected_energy_kwh": None,
            "average_peak_power_w": None,
            "confidence": 0,
        }
        policy = policy_by_program.get(program, default_program_policy(program))
        learned = program in model_programs and int(summary.get("runs", 0)) > 0
        configured = bool(policy.get("configured"))
        if learned and configured:
            status = "learned_configured"
        elif learned:
            status = "learned_unconfigured"
        else:
            status = "configured_unlearned"
        catalogue.append({
            "program": program,
            "status": status,
            "learned": learned,
            "configured": configured,
            "runs": summary.get("runs", 0),
            "profile_count": summary.get("profile_count", 0),
            "expected_runtime_minutes": summary.get("expected_runtime_minutes"),
            "expected_energy_kwh": summary.get("expected_energy_kwh"),
            "average_peak_power_w": summary.get("average_peak_power_w"),
            "confidence": summary.get("confidence", 0),
            "classification": policy.get("classification"),
            "enabled": policy.get("enabled"),
            "allow_normal_recommendation": policy.get("allow_normal_recommendation"),
            "allow_negative_price_run": policy.get("allow_negative_price_run"),
            "preference_rank": policy.get("preference_rank"),
            "minimum_days_between_runs": policy.get("minimum_days_between_runs"),
            "minimum_hours_between_runs": policy.get("minimum_hours_between_runs"),
            "maximum_runs_per_window": policy.get("maximum_runs_per_window"),
            "negative_price_priority": policy.get("negative_price_priority"),
        })
    return catalogue


def _option_or_env(options: dict, key: str, default: object = "") -> object:
    env_key = f"LOAD_OPTIMIZER_{key.upper()}"
    return os.getenv(env_key, options.get(key, default))


def instance_config(instance_id: str | dict = "1", options: dict | None = None) -> dict:
    if isinstance(instance_id, dict) and options is None:
        options = instance_id
        instance_id = "1"
    instance_id = str(instance_id)
    options = options if options is not None else load_options()
    prefix = f"instance_{instance_id}"
    tariff_entities = entity_list(options.get("tariff_entities", ""))
    single_tariff_entity = str(options.get("tariff_entity", "")).strip()
    if single_tariff_entity and single_tariff_entity not in tariff_entities:
        tariff_entities.append(single_tariff_entity)
    return {
        "instance_id": instance_id,
        "name": str(_option_or_env(options, f"{prefix}_name", f"Appliance {instance_id}")),
        "power_sensor": str(_option_or_env(options, f"{prefix}_power_sensor", "")).strip(),
        "energy_sensor": str(_option_or_env(options, f"{prefix}_energy_sensor", "")).strip(),
        "program_sensor": str(_option_or_env(options, f"{prefix}_program_sensor", "")).strip(),
        "state_sensor": str(_option_or_env(options, f"{prefix}_state_sensor", "")).strip(),
        "active_power_threshold": float(_option_or_env(options, f"{prefix}_active_power_threshold", 10)),
        "finish_delay": int(_option_or_env(options, f"{prefix}_finish_delay", 5)),
        "learning_min_runtime_minutes": float(_option_or_env(options, f"{prefix}_learning_min_runtime_minutes", 5)),
        "learning_min_samples": int(_option_or_env(options, f"{prefix}_learning_min_samples", 3)),
        "learning_min_energy_kwh": float(_option_or_env(options, f"{prefix}_learning_min_energy_kwh", 0.001)),
        "schedule_confidence_threshold": int(_option_or_env(options, f"{prefix}_schedule_confidence_threshold", 20)),
        "schedule_start_tolerance_minutes": int(_option_or_env(options, f"{prefix}_schedule_start_tolerance_minutes", 5)),
        "schedule_strategy": str(_option_or_env(options, f"{prefix}_schedule_strategy", "cheapest_absolute")),
        "schedule_equivalent_cost_tolerance_pence": float(_option_or_env(options, f"{prefix}_schedule_equivalent_cost_tolerance_pence", 0)),
        "schedule_window_preference": str(_option_or_env(options, f"{prefix}_schedule_window_preference", "any")),
        "schedule_overnight_start": str(_option_or_env(options, f"{prefix}_schedule_overnight_start", "20:00")),
        "schedule_overnight_end": str(_option_or_env(options, f"{prefix}_schedule_overnight_end", "08:00")),
        "schedule_earliest_start_entity": str(_option_or_env(options, f"{prefix}_schedule_earliest_start_entity", "")).strip(),
        "schedule_latest_finish_entity": str(_option_or_env(options, f"{prefix}_schedule_latest_finish_entity", "")).strip(),
        "program_policies": options.get(f"{prefix}_program_policies", []),
        "tariff_entity": str(options.get("tariff_entity", "")).strip(),
        "tariff_entities": tariff_entities,
        "tariff_timezone": str(options.get("tariff_timezone", "Europe/London")).strip(),
        "tariff_price_unit": str(options.get("tariff_price_unit", "p_per_kwh")),
        "cost_search_hours": int(options.get("cost_search_hours", 24)),
        "cost_forecast_hours": int(options.get("cost_forecast_hours", 12)),
        "cost_forecast_interval": int(options.get("cost_forecast_interval", 30)),
        "cost_candidate_interval": int(options.get("cost_candidate_interval", 5)),
    }


def instance_config_from_entry(entry: dict, index: int, options: dict) -> dict:
    instance_id = str(entry.get("id") or entry.get("instance_id") or index).strip()
    if not instance_id.isdigit() or int(instance_id) <= 0:
        instance_id = str(index)
    tariff_entities = entity_list(options.get("tariff_entities", ""))
    single_tariff_entity = str(options.get("tariff_entity", "")).strip()
    if single_tariff_entity and single_tariff_entity not in tariff_entities:
        tariff_entities.append(single_tariff_entity)
    return {
        "instance_id": instance_id,
        "name": str(entry.get("name") or f"Appliance {instance_id}"),
        "power_sensor": str(entry.get("power_sensor", "")).strip(),
        "energy_sensor": str(entry.get("energy_sensor", "")).strip(),
        "program_sensor": str(entry.get("program_sensor", "")).strip(),
        "state_sensor": str(entry.get("state_sensor", "")).strip(),
        "active_power_threshold": float(entry.get("active_power_threshold", 10)),
        "finish_delay": int(entry.get("finish_delay", 5)),
        "learning_min_runtime_minutes": float(entry.get("learning_min_runtime_minutes", 5)),
        "learning_min_samples": int(entry.get("learning_min_samples", 3)),
        "learning_min_energy_kwh": float(entry.get("learning_min_energy_kwh", 0.001)),
        "schedule_confidence_threshold": int(entry.get("schedule_confidence_threshold", 20)),
        "schedule_start_tolerance_minutes": int(entry.get("schedule_start_tolerance_minutes", 5)),
        "schedule_strategy": str(entry.get("schedule_strategy", "cheapest_absolute")),
        "schedule_equivalent_cost_tolerance_pence": float(entry.get("schedule_equivalent_cost_tolerance_pence", 0)),
        "schedule_window_preference": str(entry.get("schedule_window_preference", "any")),
        "schedule_overnight_start": str(entry.get("schedule_overnight_start", "20:00")),
        "schedule_overnight_end": str(entry.get("schedule_overnight_end", "08:00")),
        "schedule_earliest_start_entity": str(entry.get("schedule_earliest_start_entity", "")).strip(),
        "schedule_latest_finish_entity": str(entry.get("schedule_latest_finish_entity", "")).strip(),
        "program_policies": entry.get("program_policies", []),
        "tariff_entity": str(options.get("tariff_entity", "")).strip(),
        "tariff_entities": tariff_entities,
        "tariff_timezone": str(options.get("tariff_timezone", "Europe/London")).strip(),
        "tariff_price_unit": str(options.get("tariff_price_unit", "p_per_kwh")),
        "cost_search_hours": int(options.get("cost_search_hours", 24)),
        "cost_forecast_hours": int(options.get("cost_forecast_hours", 12)),
        "cost_forecast_interval": int(options.get("cost_forecast_interval", 30)),
        "cost_candidate_interval": int(options.get("cost_candidate_interval", 5)),
    }


def parse_config_scalar(value: str) -> object:
    value = value.strip()
    if not value:
        return ""
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return ""
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def parse_key_value(text: str) -> tuple[str, object] | None:
    if ":" not in text:
        return None
    key, value = text.split(":", 1)
    return key.strip(), parse_config_scalar(value)


def parse_instances_yaml(raw: object) -> list[dict]:
    if isinstance(raw, list):
        return [entry for entry in raw if isinstance(entry, dict)]
    raw = str(raw or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            parsed = parsed.get("instances", [])
        if isinstance(parsed, list):
            return [entry for entry in parsed if isinstance(entry, dict)]
    except json.JSONDecodeError:
        pass

    lines = [line.rstrip() for line in raw.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if lines and lines[0].strip() == "instances:":
        lines = [line[2:] if line.startswith("  ") else line for line in lines[1:]]

    instances = []
    current = None
    current_policy = None
    in_policies = False
    for line in lines:
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if indent == 0 and stripped.startswith("- "):
            current = {}
            instances.append(current)
            current_policy = None
            in_policies = False
            item = stripped[2:].strip()
            if item:
                parsed = parse_key_value(item)
                if parsed:
                    current[parsed[0]] = parsed[1]
            continue
        if current is None:
            continue
        if stripped == "program_policies:":
            current.setdefault("program_policies", [])
            current_policy = None
            in_policies = True
            continue
        if in_policies and stripped.startswith("- "):
            current_policy = {}
            current.setdefault("program_policies", []).append(current_policy)
            item = stripped[2:].strip()
            if item:
                parsed = parse_key_value(item)
                if parsed:
                    current_policy[parsed[0]] = parsed[1]
            continue
        parsed = parse_key_value(stripped)
        if not parsed:
            continue
        key, value = parsed
        if in_policies and current_policy is not None and indent >= 4:
            current_policy[key] = value
        else:
            in_policies = False
            current[key] = value
    return [entry for entry in instances if entry.get("id") or entry.get("name") or entry.get("power_sensor")]


def entity_list(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def parse_instance_ids(raw_ids: object, default: list[str] | None = None) -> list[str]:
    raw_ids = str(raw_ids)
    instance_ids = []
    for raw_id in raw_ids.split(","):
        instance_id = raw_id.strip()
        if instance_id.isdigit() and int(instance_id) > 0 and instance_id not in instance_ids:
            instance_ids.append(instance_id)
    return instance_ids or (default if default is not None else [])


def reset_request_status(database: dict, options: dict) -> dict:
    raw_reset = str(options.get("reset_instance_ids", "")).strip()
    if not raw_reset:
        return {
            "reset_status": "idle",
            "reset_requested_instance_ids": [],
            "reset_processed_instance_ids": [],
            "reset_pending_instance_ids": [],
            "reset_invalid_tokens": [],
            "reset_message": "No reset request is configured.",
        }

    requested = parse_instance_ids(raw_reset)
    invalid = [
        token.strip()
        for token in raw_reset.split(",")
        if token.strip() and token.strip() not in requested
    ]
    processed = sorted(
        {
            str(instance_id)
            for instance_id in database.get("processed_reset_instance_ids", [])
            if str(instance_id).isdigit()
        },
        key=int,
    )
    pending = [instance_id for instance_id in requested if instance_id not in processed]

    if pending:
        status = "pending"
        message = f"Reset pending for instance(s): {', '.join(pending)}."
    elif requested:
        status = "consumed"
        message = (
            f"Reset request has already been applied for instance(s): "
            f"{', '.join(requested)}."
        )
    else:
        status = "invalid"
        message = "Reset request does not contain any valid positive instance IDs."

    if invalid and status != "invalid":
        status = "partially_invalid"
        message = f"{message} Ignored invalid value(s): {', '.join(invalid)}."

    return {
        "reset_status": status,
        "reset_requested_instance_ids": requested,
        "reset_processed_instance_ids": processed,
        "reset_pending_instance_ids": pending,
        "reset_invalid_tokens": invalid,
        "reset_message": message,
    }


def reset_configured_instances(database: dict, options: dict) -> list[str]:
    raw_reset = str(options.get("reset_instance_ids", "")).strip()
    if not raw_reset:
        database.pop("processed_reset_instance_ids", None)
        return []
    reset_ids = parse_instance_ids(raw_reset)
    processed = set(database.get("processed_reset_instance_ids", []))
    reset_ids = [instance_id for instance_id in reset_ids if instance_id not in processed]
    if not reset_ids:
        return []
    instances = database.setdefault("instances", {})
    removed = []
    for instance_id in reset_ids:
        if instance_id in instances:
            instances.pop(instance_id, None)
            removed.append(instance_id)
        processed.add(instance_id)
    database["processed_reset_instance_ids"] = sorted(processed, key=int)
    if removed:
        LOGGER.warning("Reset Load Optimizer instance data for: %s", ", ".join(removed))
    return removed


def running_instances(database: dict, configs: list[dict]) -> list[dict]:
    instances = database.get("instances", {})
    running = []
    for config in configs:
        instance_id = str(config["instance_id"])
        instance = instances.get(instance_id, {})
        if instance.get("cycle_start"):
            running.append({
                "instance_id": instance_id,
                "name": config["name"],
                "cycle_start": instance["cycle_start"],
            })
    return running


def mark_interrupted_captures(database: dict, running: list[dict]) -> None:
    instances = database.setdefault("instances", {})
    for item in running:
        instance = instances.get(str(item["instance_id"]))
        if instance and instance.get("cycle_start"):
            instance["capture_interrupted"] = True
            instance["capture_interrupted_at"] = datetime.now(timezone.utc).isoformat()


def publish_restart_warning(token: str, running: list[dict]) -> None:
    if not running:
        return
    lines = [
        f"- Instance {item['instance_id']} ({item['name']}) started at {item['cycle_start']}"
        for item in running
    ]
    api_request(token, "/services/persistent_notification/create", {
        "notification_id": "load_optimizer_restart_running_cycle",
        "title": "Load Optimizer restarted during a cycle",
        "message": (
            "Load Optimizer started while one or more appliance cycles were already "
            "being tracked. The current cycle data may be incomplete or split.\n\n"
            + "\n".join(lines)
        ),
    })


def publish_restart_safety(token: str, running: list[dict]) -> None:
    blocked = bool(running)
    publish_entity(token, RESTART_SAFETY_ENTITY, "blocked" if blocked else "safe", {
        "friendly_name": "Load Optimizer Restart Safety",
        "icon": "mdi:restart-alert" if blocked else "mdi:restart",
        "restart_blocked": blocked,
        "active_capture_count": len(running),
        "active_capture_instances": running,
        "message": (
            "Do not restart or update Load Optimizer while appliance cycle capture is active."
            if blocked else
            "No active appliance captures. Restart or update is safe."
        ),
    })


def instance_configs(options: dict | None = None) -> list[dict]:
    options = options if options is not None else load_options()
    configured_instances_yaml = parse_instances_yaml(options.get("instances_yaml", ""))
    if configured_instances_yaml:
        return [
            instance_config_from_entry(entry, index, options)
            for index, entry in enumerate(configured_instances_yaml, start=1)
            if isinstance(entry, dict)
        ]
    configured_instances = options.get("instances")
    if isinstance(configured_instances, list) and configured_instances:
        return [
            instance_config_from_entry(entry, index, options)
            for index, entry in enumerate(configured_instances, start=1)
            if isinstance(entry, dict)
        ]
    return []


def schedule_advice(result: dict, config: dict, now: datetime) -> dict:
    if result.get("status") != "ready" or not result.get("start"):
        return {
            "status": result.get("status", "not_ready"),
            "program": "none",
            "recommended_start": "unknown",
            "good_to_start": False,
            "automation_ready": False,
            "reason": result.get("reason") or result.get("status", "not_ready"),
        }
    start = result["start"].astimezone(timezone.utc)
    now = now.astimezone(timezone.utc)
    confidence = int(result.get("confidence") or 0)
    confidence_threshold = int(config.get("schedule_confidence_threshold", 20))
    tolerance_minutes = int(config.get("schedule_start_tolerance_minutes", 5))
    seconds_until_start = round((start - now).total_seconds())
    good_to_start = abs(seconds_until_start) <= tolerance_minutes * 60
    automation_ready = good_to_start and confidence >= confidence_threshold
    if confidence < confidence_threshold:
        reason = f"confidence_below_{confidence_threshold}"
    elif seconds_until_start > tolerance_minutes * 60:
        reason = "recommended_start_in_future"
    elif seconds_until_start < -tolerance_minutes * 60:
        reason = "recommended_start_passed"
    else:
        reason = "ready"
    return {
        "status": "ready",
        "program": result.get("program", "none"),
        "recommended_start": start.isoformat(),
        "recommended_finish": result.get("finish").isoformat() if result.get("finish") else None,
        "seconds_until_start": seconds_until_start,
        "good_to_start": good_to_start,
        "automation_ready": automation_ready,
        "reason": reason,
        "confidence": confidence,
        "confidence_threshold": confidence_threshold,
        "start_tolerance_minutes": tolerance_minutes,
        "estimated_cost_pence": result.get("total_cost_pence"),
        "cost_if_started_now_pence": result.get("cost_if_started_now_pence"),
        "potential_saving_pence": result.get("potential_saving_pence"),
        "overnight_comparison": result.get("overnight_comparison"),
        "daytime_comparison": result.get("daytime_comparison"),
        "negative_price_run": result.get("negative_price_run", False),
        "schedule_strategy": result.get("schedule_strategy"),
        "equivalent_cost_tolerance_pence": result.get("equivalent_cost_tolerance_pence"),
        "window_preference": result.get("window_preference"),
        "is_overnight_start": result.get("is_overnight_start"),
        "is_daytime_start": result.get("is_daytime_start"),
        "overnight_window": {
            "start": result.get("overnight_start"),
            "end": result.get("overnight_end"),
            "timezone": result.get("schedule_timezone"),
        },
        "schedule_earliest_start_entity": result.get("schedule_earliest_start_entity"),
        "schedule_latest_finish_entity": result.get("schedule_latest_finish_entity"),
        "constraints": {
            "earliest_allowed_start": result.get("earliest_allowed_start"),
            "latest_allowed_finish": result.get("latest_allowed_finish"),
            "rejected_constraints": result.get("rejected_constraints", 0),
            "rejected_cooldowns": result.get("rejected_cooldowns", 0),
        },
        "program_diagnostics": result.get("program_diagnostics", []),
    }


def publish_cost_entities(token: str, prefix: str, name: str, result: dict) -> None:
    status = result.get("status", "error")
    common = {
        "tariff_entity": result.get("tariff_entity"),
        "tariff_entities": result.get("tariff_entities", []),
        "tariff_periods": result.get("tariff_periods", 0),
        "tariff_start": result.get("tariff_start"),
        "tariff_end": result.get("tariff_end"),
        "reason": result.get("reason"),
        "schedule_earliest_start_entity": result.get("schedule_earliest_start_entity"),
        "schedule_latest_finish_entity": result.get("schedule_latest_finish_entity"),
        "constraints": {
            "earliest_allowed_start": result.get("earliest_allowed_start"),
            "latest_allowed_finish": result.get("latest_allowed_finish"),
            "rejected_constraints": result.get("rejected_constraints", 0),
            "rejected_cooldowns": result.get("rejected_cooldowns", 0),
        },
        "program_diagnostics": result.get("program_diagnostics", []),
    }
    if result.get("tariff_diagnostics") is not None:
        common["tariff_diagnostics"] = result["tariff_diagnostics"]
    if result.get("tariff_parse_errors") is not None:
        common["tariff_parse_errors"] = result["tariff_parse_errors"]
    publish_entity(token, f"{prefix}_cost_status", status, {
        "friendly_name": f"{name} Cost Status",
        "icon": "mdi:currency-gbp",
        **common,
    })
    ready = status == "ready"
    overnight_comparison = result.get("overnight_comparison") or {}
    daytime_comparison = result.get("daytime_comparison") or {}
    cost_forecast = result.get("cost_forecast", []) if ready else []

    def rounded_pence(value):
        if value is None or value == "unknown":
            return "unknown"
        return round(float(value), 2)

    values = (
        ("cost_if_started_now", rounded_pence(result.get("cost_if_started_now_pence")) if ready else "unknown", "p", "mdi:cash-clock"),
        ("cheapest_start", result.get("start").isoformat() if ready else "unknown", None, "mdi:clock-start"),
        ("cheapest_cost", rounded_pence(result.get("total_cost_pence")) if ready else "unknown", "p", "mdi:cash-check"),
        ("overnight_cost", rounded_pence(overnight_comparison.get("cost_pence")) if ready and overnight_comparison else "unknown", "p", "mdi:weather-night"),
        ("daytime_cost", rounded_pence(daytime_comparison.get("cost_pence")) if ready and daytime_comparison else "unknown", "p", "mdi:white-balance-sunny"),
        ("potential_saving", rounded_pence(result.get("potential_saving_pence")) if ready else "unknown", "p", "mdi:piggy-bank"),
        ("overnight_saving", rounded_pence(overnight_comparison.get("saving_vs_now_pence")) if ready and overnight_comparison else "unknown", "p", "mdi:weather-night"),
        ("daytime_saving", rounded_pence(daytime_comparison.get("saving_vs_now_pence")) if ready and daytime_comparison else "unknown", "p", "mdi:white-balance-sunny"),
        ("cost_confidence", result.get("confidence") if ready else "unknown", "%", "mdi:gauge"),
        ("recommended_program", result.get("program") if ready else "none", None, "mdi:playlist-check"),
    )
    for suffix, value, unit, icon in values:
        attributes = {
            "friendly_name": f"{name} {suffix.replace('_', ' ').title()}",
            "icon": icon,
            **common,
        }
        if unit:
            attributes["unit_of_measurement"] = unit
        if suffix == "cheapest_start":
            attributes["device_class"] = "timestamp"
        if ready:
            attributes.update({
                "program": result.get("program"),
                "energy_kwh": result.get("energy_kwh"),
                "energy_cost_pence": result.get("energy_cost_pence"),
                "overhead_cost_pence": result.get("overhead_cost_pence"),
                "negative_price_run": result.get("negative_price_run"),
                "candidate_count": result.get("candidate_count"),
                "comparison_candidate_count": result.get("comparison_candidate_count"),
                "recommended_finish": result.get("finish").isoformat() if result.get("finish") else None,
                "schedule_strategy": result.get("schedule_strategy"),
                "equivalent_cost_tolerance_pence": result.get("equivalent_cost_tolerance_pence"),
                "window_preference": result.get("window_preference"),
                "is_overnight_start": result.get("is_overnight_start"),
                "is_daytime_start": result.get("is_daytime_start"),
                "overnight_window": {
                    "start": result.get("overnight_start"),
                    "end": result.get("overnight_end"),
                    "timezone": result.get("schedule_timezone"),
                },
                "constraints": {
                    "earliest_allowed_start": result.get("earliest_allowed_start"),
                    "latest_allowed_finish": result.get("latest_allowed_finish"),
                    "rejected_constraints": result.get("rejected_constraints", 0),
                    "rejected_cooldowns": result.get("rejected_cooldowns", 0),
                },
                "program_diagnostics": result.get("program_diagnostics", []),
                "overnight_comparison": result.get("overnight_comparison"),
                "daytime_comparison": result.get("daytime_comparison"),
                "forecast_hours": result.get("forecast_hours"),
                "forecast_interval_minutes": result.get("forecast_interval_minutes"),
            })
            if suffix.startswith("overnight_") and result.get("overnight_comparison"):
                attributes.update(result["overnight_comparison"])
            if suffix.startswith("daytime_") and result.get("daytime_comparison"):
                attributes.update(result["daytime_comparison"])
            if suffix in {"cheapest_cost", "cheapest_start", "recommended_program"}:
                attributes["cost_breakdown"] = result.get("cost_breakdown", [])
                attributes["breakdown_format"] = "start, end, price_p_per_kwh, energy_kwh, energy_cost_pence"
            if suffix == "cost_if_started_now":
                attributes["cost_breakdown"] = result.get("cost_if_started_now_breakdown", [])
                attributes["breakdown_format"] = "start, end, price_p_per_kwh, energy_kwh, energy_cost_pence"
        publish_entity(token, f"{prefix}_{suffix}", value if value is not None else "unknown", attributes)
    for intent, icon in (
        ("now", "mdi:play-circle"),
        ("soon", "mdi:clock-fast"),
        ("overnight", "mdi:weather-night"),
        ("negative_price", "mdi:transmission-tower-export"),
    ):
        recommendation = result.get(f"{intent}_recommendation") or {}
        recommendation_ready = ready and recommendation.get("status") == "ready"
        state = recommendation.get("program") if recommendation_ready else recommendation.get("status", "not_ready")
        attributes = {
            "friendly_name": f"{name} {intent.title()} Recommendation",
            "icon": icon,
            **common,
            "intent": intent,
            "status": recommendation.get("status", "not_ready"),
            "reason": recommendation.get("reason"),
            "program": recommendation.get("program"),
            "start": recommendation.get("start"),
            "finish": recommendation.get("finish"),
            "seconds_until_start": recommendation.get("seconds_until_start"),
            "cost_pence": rounded_pence(recommendation.get("cost_pence")) if recommendation_ready else None,
            "saving_vs_now_pence": rounded_pence(recommendation.get("saving_vs_now_pence")) if recommendation_ready else None,
            "energy_kwh": recommendation.get("energy_kwh"),
            "energy_kwh_per_minute": recommendation.get("energy_kwh_per_minute"),
            "confidence": recommendation.get("confidence"),
            "ready_to_start": recommendation.get("ready_to_start", False),
            "negative_price_run": recommendation.get("negative_price_run"),
            "is_overnight_start": recommendation.get("is_overnight_start"),
            "is_daytime_start": recommendation.get("is_daytime_start"),
        }
        publish_entity(token, f"{prefix}_{intent}_recommendation", state or "not_ready", attributes)
    forecast_costs = [
        float(row["cost_pence"]) for row in cost_forecast
        if row.get("cost_pence") is not None
    ]
    publish_entity(token, f"{prefix}_cost_forecast", rounded_pence(min(forecast_costs)) if forecast_costs else "unknown", {
        "friendly_name": f"{name} Cost Forecast",
        "icon": "mdi:chart-line",
        "unit_of_measurement": "p",
        **common,
        "forecast_hours": result.get("forecast_hours") if ready else None,
        "forecast_interval_minutes": result.get("forecast_interval_minutes") if ready else None,
        "forecast_points": len(cost_forecast),
        "forecast_diagnostics": result.get("forecast_diagnostics", []) if ready else [],
        "forecast": cost_forecast,
        "forecast_format": "program, start, finish, cost_pence, energy_kwh, confidence, is_overnight_start, is_daytime_start",
    })


def publish_schedule_entities(token: str, prefix: str, name: str, advice: dict) -> None:
    common = {
        "program": advice.get("program"),
        "recommended_start": advice.get("recommended_start"),
        "seconds_until_start": advice.get("seconds_until_start"),
        "good_to_start": advice.get("good_to_start"),
        "automation_ready": advice.get("automation_ready"),
        "reason": advice.get("reason"),
        "confidence": advice.get("confidence"),
        "confidence_threshold": advice.get("confidence_threshold"),
        "start_tolerance_minutes": advice.get("start_tolerance_minutes"),
        "estimated_cost_pence": advice.get("estimated_cost_pence"),
        "cost_if_started_now_pence": advice.get("cost_if_started_now_pence"),
        "potential_saving_pence": advice.get("potential_saving_pence"),
        "negative_price_run": advice.get("negative_price_run"),
        "recommended_finish": advice.get("recommended_finish"),
        "schedule_strategy": advice.get("schedule_strategy"),
        "equivalent_cost_tolerance_pence": advice.get("equivalent_cost_tolerance_pence"),
        "window_preference": advice.get("window_preference"),
        "is_overnight_start": advice.get("is_overnight_start"),
        "is_daytime_start": advice.get("is_daytime_start"),
        "overnight_window": advice.get("overnight_window"),
        "constraints": advice.get("constraints"),
    }
    publish_entity(token, f"{prefix}_schedule_status", advice.get("status", "not_ready"), {
        "friendly_name": f"{name} Schedule Status",
        "icon": "mdi:calendar-clock",
        **common,
    })
    publish_entity(token, f"{prefix}_recommended_start", advice.get("recommended_start", "unknown"), {
        "friendly_name": f"{name} Recommended Start",
        "device_class": "timestamp",
        "icon": "mdi:clock-start",
        **common,
    })
    publish_entity(token, f"{prefix}_recommended_finish", advice.get("recommended_finish") or "unknown", {
        "friendly_name": f"{name} Recommended Finish",
        "device_class": "timestamp",
        "icon": "mdi:clock-end",
        **common,
    })
    estimated_cost = advice.get("estimated_cost_pence")
    try:
        estimated_cost_state = round(float(estimated_cost), 2)
    except (TypeError, ValueError):
        estimated_cost_state = "unknown"
    publish_entity(token, f"{prefix}_estimated_scheduled_cost", estimated_cost_state, {
        "friendly_name": f"{name} Estimated Scheduled Cost",
        "unit_of_measurement": "p",
        "icon": "mdi:cash-fast",
        **common,
    })
    publish_entity(token, f"{prefix}_good_to_start", "on" if advice.get("good_to_start") else "off", {
        "friendly_name": f"{name} Good To Start",
        "device_class": "running",
        "icon": "mdi:play-circle",
        **common,
    })


def update_instance(token: str, database: dict, config: dict, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    instance_id = str(config.get("instance_id", "1"))
    instance = database.setdefault("instances", {}).setdefault(instance_id, {})
    power_entity = source_state(token, config["power_sensor"])
    energy_entity = source_state(token, config["energy_sensor"])
    program_entity = source_state(token, config["program_sensor"])
    device_state_entity = source_state(token, config["state_sensor"])
    power = numeric_state(power_entity)
    energy = numeric_state(energy_entity)
    prefix = f"sensor.load_optimizer_{instance_id}"
    name = config["name"]

    configured = bool(config["power_sensor"])
    publish_entity(token, f"{prefix}_status", "ready" if configured else "configuration_required", {
        "friendly_name": f"{name} Optimizer Status", "icon": "mdi:progress-wrench",
        "power_sensor": config["power_sensor"] or None, "energy_sensor": config["energy_sensor"] or None,
    })
    publish_entity(token, f"{prefix}_power", power if power is not None else "unavailable", {
        "friendly_name": f"{name} Power", "device_class": "power", "unit_of_measurement": "W",
        "state_class": "measurement", "source_entity": config["power_sensor"] or None,
    })
    publish_entity(token, f"{prefix}_energy", energy if energy is not None else "unavailable", {
        "friendly_name": f"{name} Energy", "device_class": "energy", "unit_of_measurement": "kWh",
        "state_class": "total_increasing", "source_entity": config["energy_sensor"] or None,
    })
    program = normalise_program(program_entity["state"] if program_entity else None)
    publish_entity(token, f"{prefix}_program", program, {
        "friendly_name": f"{name} Program", "icon": "mdi:format-list-bulleted", "source_entity": config["program_sensor"] or None,
    })

    active = power is not None and power >= config["active_power_threshold"]
    if active:
        if not instance.get("cycle_start"):
            instance.update(cycle_start=now.isoformat(), start_energy=energy, peak_power=power, samples=0, profile=[], below_threshold=0)
        start = datetime.fromisoformat(instance["cycle_start"])
        instance.setdefault("profile", []).append(profile_sample(start, now, power, energy))
        instance["samples"] = len(instance["profile"])
        instance["peak_power"] = max(float(instance.get("peak_power", 0)), power)
        instance["below_threshold"] = 0
        instance.pop("finish_candidate", None)
    elif instance.get("cycle_start"):
        start = datetime.fromisoformat(instance["cycle_start"])
        instance.setdefault("profile", []).append(profile_sample(start, now, power, energy))
        instance["samples"] = len(instance["profile"])
        instance["below_threshold"] = int(instance.get("below_threshold", 0)) + 1
        if not instance.get("finish_candidate"):
            instance["finish_candidate"] = {
                "time": now.isoformat(),
                "energy": energy,
                "profile_length": len(instance["profile"]),
            }
        if instance["below_threshold"] >= config["finish_delay"]:
            finish_candidate = instance["finish_candidate"]
            finish = datetime.fromisoformat(finish_candidate["time"])
            finish_energy = finish_candidate.get("energy")
            completed_profile = instance["profile"][:finish_candidate["profile_length"]]
            profile_energy = profile_energy_kwh(completed_profile)
            sensor_energy = (
                round(max(0.0, finish_energy - instance["start_energy"]), 4)
                if finish_energy is not None and instance.get("start_energy") is not None
                else None
            )
            last = {
                "program": instance.get("program") or program,
                "runtime_minutes": round((finish - start).total_seconds() / 60, 1),
                "energy_kwh": profile_energy if profile_energy is not None else sensor_energy,
                "energy_source": "power_profile" if profile_energy is not None else "energy_sensor_delta",
                "energy_sensor_delta_kwh": sensor_energy,
                "peak_power": instance.get("peak_power", 0),
                "sample_count": len(completed_profile),
                "power_profile": completed_profile,
                "finish": finish.isoformat(),
            }
            if instance.get("capture_interrupted"):
                last["learning_excluded"] = True
                last["exclusion_reason"] = "app_restarted_during_cycle"
                instance["last_discarded_cycle"] = last
            elif quality_issue := cycle_quality_issue(config, last):
                last["learning_excluded"] = True
                last["exclusion_reason"] = quality_issue
                instance["last_discarded_cycle"] = last
                excluded = instance.setdefault("quality_excluded_cycles", [])
                excluded.append({
                    "program": normalise_program(last.get("program")),
                    "finish": last.get("finish"),
                    "runtime_minutes": last.get("runtime_minutes"),
                    "energy_kwh": last.get("energy_kwh"),
                    "peak_power_w": last.get("peak_power"),
                    "sample_count": last.get("sample_count"),
                    "energy_source": last.get("energy_source"),
                    "learning_excluded": True,
                    "exclusion_reason": quality_issue,
                })
                del excluded[:-20]
            else:
                instance["last_cycle"] = last
                update_program_model(instance, last)
                instance["runs"] = int(instance.get("runs", 0)) + 1
            for key in ("cycle_start", "start_energy", "peak_power", "samples", "profile", "below_threshold", "finish_candidate", "program", "capture_interrupted", "capture_interrupted_at"):
                instance.pop(key, None)
    if instance.get("cycle_start") and program not in ("unknown", "unavailable", ""):
        instance["program"] = program

    cycle_state = "running" if instance.get("cycle_start") else "idle"
    publish_entity(token, f"{prefix}_cycle_state", cycle_state, {
        "friendly_name": f"{name} Cycle State", "icon": "mdi:dishwasher" if "dishwasher" in name.lower() else "mdi:lightning-bolt",
        "source_state": device_state_entity["state"] if device_state_entity else None,
    })
    publish_entity(token, f"{prefix}_sample_count", instance.get("samples", instance.get("last_cycle", {}).get("sample_count", 0)), {
        "friendly_name": f"{name} Cycle Samples", "state_class": "measurement", "icon": "mdi:counter",
    })
    publish_entity(token, f"{prefix}_peak_power", instance.get("peak_power", instance.get("last_cycle", {}).get("peak_power", 0)), {
        "friendly_name": f"{name} Peak Power", "device_class": "power", "unit_of_measurement": "W", "state_class": "measurement",
    })
    last = instance.get("last_cycle", {})
    models = instance.get("program_models", {})
    policies = resolve_program_policies(models, config.get("program_policies", []))
    policy_defaults = default_program_policy("program")
    policy_defaults.pop("program")
    publish_entity(token, f"{prefix}_program_policies", len(policies), {
        "friendly_name": f"{name} Program Policies",
        "icon": "mdi:shield-check",
        "policies": policies,
        "classifications": sorted(PROGRAM_CLASSIFICATIONS),
        "optional_field_defaults": policy_defaults,
    })
    catalogue = program_catalogue(models, policies)
    publish_entity(token, f"{prefix}_program_catalogue", len(catalogue), {
        "friendly_name": f"{name} Program Catalogue",
        "icon": "mdi:format-list-checks",
        "programs": catalogue,
        "statuses": sorted({item["status"] for item in catalogue}),
        "status_meanings": {
            "learned_configured": "Program has learned run data and an explicit policy.",
            "learned_unconfigured": "Program has been observed but has no explicit policy.",
            "configured_unlearned": "Program is configured in policy but has no learned runs yet.",
        },
    })
    discovered = [item for item in catalogue if item["status"] == "learned_unconfigured"]
    publish_entity(token, f"{prefix}_discovered_programs", len(discovered), {
        "friendly_name": f"{name} Discovered Programs",
        "icon": "mdi:alert-decagram",
        "programs": discovered,
        "message": (
            "Review newly observed programs and add explicit program policies."
            if discovered else
            "No newly observed unconfigured programs."
        ),
    })
    summaries = [program_summary(program_name, model) for program_name, model in sorted(models.items())]
    tariff_entities = config.get("tariff_entities", [])
    cost_result = {
        "status": "tariff_not_configured",
        "tariff_entity": config.get("tariff_entity"),
        "tariff_entities": tariff_entities,
    }
    if tariff_entities:
        earliest_start_entity = config.get("schedule_earliest_start_entity")
        latest_finish_entity = config.get("schedule_latest_finish_entity")
        earliest_start_utc = datetime_from_entity_state(source_state(token, earliest_start_entity)) if earliest_start_entity else None
        latest_finish_utc = datetime_from_entity_state(source_state(token, latest_finish_entity)) if latest_finish_entity else None
        if earliest_start_utc and earliest_start_utc <= now.astimezone(timezone.utc):
            earliest_start_utc = None
        if latest_finish_utc and latest_finish_utc <= now.astimezone(timezone.utc):
            latest_finish_utc = None
        tariff_states = []
        missing_entities = []
        for entity_id in tariff_entities:
            tariff_state = tariff_state_from_entity(token, entity_id)
            if tariff_state is None:
                missing_entities.append(entity_id)
            else:
                tariff_states.append(tariff_state)
        if missing_entities:
            cost_result = {
                "status": "tariff_unavailable",
                "tariff_entity": ", ".join(tariff_entities),
                "tariff_entities": tariff_entities,
                "reason": f"Home Assistant tariff entities could not be read: {', '.join(missing_entities)}",
            }
        else:
            tariff_diagnostics = [tariff_entity_diagnostic(state) for state in tariff_states]
            try:
                periods = []
                tariff_parse_errors = []
                for tariff_state in tariff_states:
                    try:
                        periods.extend(tariff_periods_from_entity(
                            tariff_state,
                            reference_utc=now,
                            timezone_name=config["tariff_timezone"],
                            price_unit=config["tariff_price_unit"],
                        ))
                    except (TypeError, ValueError) as error:
                        tariff_parse_errors.append({
                            "entity_id": tariff_state.get("entity_id"),
                            "reason": str(error),
                        })
                if not periods:
                    raise ValueError("No configured tariff entity produced a supported future-rate attribute")
                periods.sort(key=lambda period: period["start"])
                cost_result = recommend_cycle(
                    summaries,
                    policies,
                    periods,
                    reference_utc=now,
                    search_hours=config["cost_search_hours"],
                    candidate_interval_minutes=config["cost_candidate_interval"],
                    schedule_strategy=config.get("schedule_strategy", "cheapest_absolute"),
                    equivalent_cost_tolerance_pence=config.get("schedule_equivalent_cost_tolerance_pence", 0),
                    window_preference=config.get("schedule_window_preference", "any"),
                    overnight_start=config.get("schedule_overnight_start", "20:00"),
                    overnight_end=config.get("schedule_overnight_end", "08:00"),
                    schedule_timezone=config.get("tariff_timezone", "Europe/London"),
                    earliest_start_utc=earliest_start_utc,
                    latest_finish_utc=latest_finish_utc,
                    forecast_hours=config.get("cost_forecast_hours", 12),
                    forecast_interval_minutes=config.get("cost_forecast_interval", 30),
                )
                cost_result.update({
                    "tariff_entity": ", ".join(tariff_entities),
                    "tariff_entities": tariff_entities,
                    "tariff_periods": len(periods),
                    "tariff_start": periods[0]["start"].isoformat(),
                    "tariff_end": periods[-1]["end"].isoformat(),
                    "tariff_diagnostics": tariff_diagnostics,
                    "tariff_parse_errors": tariff_parse_errors,
                    "schedule_earliest_start_entity": earliest_start_entity,
                    "schedule_latest_finish_entity": latest_finish_entity,
                })
            except (TypeError, ValueError) as error:
                cost_result = {
                    "status": "tariff_invalid",
                    "tariff_entity": ", ".join(tariff_entities),
                    "tariff_entities": tariff_entities,
                    "tariff_diagnostics": tariff_diagnostics,
                    "reason": str(error),
                }
    publish_cost_entities(token, prefix, name, cost_result)
    publish_schedule_entities(token, prefix, name, schedule_advice(cost_result, config, now))
    latest_program = normalise_program(last.get("program"))
    selected_program = latest_program if latest_program in models else (next(iter(sorted(models)), None))
    selected_summary = program_summary(selected_program, models[selected_program]) if selected_program else {}
    publish_entity(token, f"{prefix}_learned_programs", len(models), {
        "friendly_name": f"{name} Learned Programs",
        "icon": "mdi:database-check",
        "programs": summaries,
    })
    publish_entity(token, f"{prefix}_program_model", selected_program or "none", {
        "friendly_name": f"{name} Program Model",
        "icon": "mdi:chart-bell-curve-cumulative",
        **selected_summary,
        "profile_format": ["progress_percent", "power_w"],
        "representative_profile": [
            [round(index * 100 / (len(selected_summary.get("representative_profile_w", [])) - 1), 1), power]
            for index, power in enumerate(selected_summary.get("representative_profile_w", []))
        ] if len(selected_summary.get("representative_profile_w", [])) > 1 else [],
    })
    profile = last.get("power_profile", [])
    profile_payload = compact_profile_data(models, last)
    publish_entity(token, f"{prefix}_profile_data", len(profile_payload["program_profiles"]), {
        "friendly_name": f"{name} Profile Data",
        "icon": "mdi:chart-line",
        **profile_payload,
    })
    publish_entity(token, f"{prefix}_last_profile", "ready" if profile else "none", {
        "friendly_name": f"{name} Last Power Profile",
        "icon": "mdi:chart-line",
        "program": normalise_program(last.get("program")),
        "runtime_minutes": last.get("runtime_minutes"),
        "energy_kwh": last.get("energy_kwh"),
        "energy_source": last.get("energy_source"),
        "energy_sensor_delta_kwh": last.get("energy_sensor_delta_kwh"),
        "sample_count": len(profile),
        "samples": [[sample["offset_seconds"], sample.get("power_w")] for sample in profile],
        "sample_format": ["offset_seconds", "power_w"],
    })
    discarded = instance.get("last_discarded_cycle", {})
    publish_entity(token, f"{prefix}_last_discarded_cycle", "ready" if discarded else "none", {
        "friendly_name": f"{name} Last Discarded Cycle",
        "icon": "mdi:delete-clock",
        "program": normalise_program(discarded.get("program")),
        "finish": discarded.get("finish"),
        "runtime_minutes": discarded.get("runtime_minutes"),
        "energy_kwh": discarded.get("energy_kwh"),
        "sample_count": discarded.get("sample_count"),
        "peak_power_w": discarded.get("peak_power_w", discarded.get("peak_power")),
        "learning_excluded": discarded.get("learning_excluded", False),
        "exclusion_reason": discarded.get("exclusion_reason"),
        "quality_excluded_cycles": instance.get("quality_excluded_cycles", []),
    })
    for suffix, value, attrs in (
        ("last_program", normalise_program(last.get("program")), {"icon": "mdi:format-list-bulleted"}),
        ("last_runtime", last.get("runtime_minutes", 0), {"unit_of_measurement": "min", "device_class": "duration"}),
        ("last_energy", last.get("energy_kwh", 0) if last.get("energy_kwh") is not None else "unknown", {"unit_of_measurement": "kWh", "device_class": "energy"}),
        ("last_finish", last.get("finish", "unknown"), {"device_class": "timestamp"}),
        ("total_runs", instance.get("runs", 0), {"state_class": "total", "icon": "mdi:counter"}),
    ):
        publish_entity(token, f"{prefix}_{suffix}", value, {"friendly_name": f"{name} {suffix.replace('_', ' ').title()}", **attrs})


def publish_status(
    token: str,
    instance_count: int,
    running: list[dict] | None = None,
    reset_status: dict | None = None,
) -> None:
    running = running or []
    publish_entity(token, STATUS_ENTITY, "running", {
        "friendly_name": "Load Optimizer Status", "icon": "mdi:transmission-tower",
        "version": APP_VERSION, "instances": instance_count,
        "restart_blocked": bool(running),
        "active_capture_instances": running,
        **(reset_status or {}),
    })


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path != "/health":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, _format: str, *_args: object) -> None:
        return


def run_health_server() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0", 8099), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def stop(_signum: int, _frame: object) -> None:
    STOP_EVENT.set()


def main() -> None:
    configure_logging()
    token = os.getenv("SUPERVISOR_TOKEN")
    if not token:
        raise RuntimeError("SUPERVISOR_TOKEN was not provided by Home Assistant")

    interval = max(10, int(os.getenv("LOAD_OPTIMIZER_SCAN_INTERVAL", "60")))
    options = load_options()
    state = load_state()
    reset_configured_instances(state, options)
    configs = instance_configs(options)
    bootstrap_program_models(state)
    repair_learning_quality(state, configs)
    startup_running = running_instances(state, configs)
    mark_interrupted_captures(state, startup_running)
    save_state(state)
    health_server = run_health_server()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    LOGGER.info("Load Optimizer %s started", APP_VERSION)
    publish_restart_warning(token, startup_running)
    publish_restart_safety(token, startup_running)

    try:
        while not STOP_EVENT.is_set():
            for config in configs:
                update_instance(token, state, config)
            save_state(state)
            active_captures = running_instances(state, configs)
            publish_status(
                token,
                len(configs),
                active_captures,
                reset_request_status(state, options),
            )
            publish_restart_safety(token, active_captures)
            STOP_EVENT.wait(interval)
    finally:
        health_server.shutdown()
        LOGGER.info("Load Optimizer stopped")


if __name__ == "__main__":
    main()
