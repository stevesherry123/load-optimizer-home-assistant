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

APP_VERSION = "0.6.1"
API_BASE_URL = "http://supervisor/core/api"
DATA_PATH = Path("/data/load_optimizer.json")
OPTIONS_PATH = Path("/data/options.json")
STATUS_ENTITY = "sensor.load_optimizer_status"

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


def publish_entity(token: str, entity_id: str, state: object, attributes: dict) -> None:
    api_request(token, f"/states/{entity_id}", {"state": str(state), "attributes": attributes})


def source_state(token: str, entity_id: str) -> dict | None:
    if not entity_id:
        return None
    return api_request(token, f"/states/{entity_id}")


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
        "expected_runtime_minutes": runtime,
        "runtime_stddev_minutes": runtime_stddev,
        "expected_energy_kwh": energy,
        "energy_stddev_kwh": energy_stddev,
        "average_peak_power_w": peak,
        "confidence": confidence,
        "representative_profile_w": model.get("representative_profile_w", []),
    }


def update_program_model(instance: dict, cycle: dict) -> dict:
    program = normalise_program(cycle.get("program"))
    if program == "unknown":
        program = "Default"
    model = instance.setdefault("program_models", {}).setdefault(program, {"runs": 0})
    model["runs"] += 1
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
    return program_summary(program, model)


def bootstrap_program_models(database: dict) -> None:
    for instance in database.get("instances", {}).values():
        if "program_models" not in instance and instance.get("last_cycle"):
            update_program_model(instance, instance["last_cycle"])


def default_program_policy(program: str) -> dict:
    return {
        "program": program,
        "classification": "unclassified",
        "enabled": True,
        "preference_rank": 50,
        "allow_normal_recommendation": False,
        "allow_negative_price_run": False,
        "minimum_days_between_runs": 0,
        "maximum_runs_per_window": 1,
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
        "classification": classification,
        "enabled": bool(raw.get("enabled", policy["enabled"])),
        "preference_rank": max(1, min(100, int(raw.get("preference_rank", policy["preference_rank"])))),
        "allow_normal_recommendation": bool(raw.get("allow_normal_recommendation", policy["allow_normal_recommendation"])),
        "allow_negative_price_run": bool(raw.get("allow_negative_price_run", policy["allow_negative_price_run"])),
        "minimum_days_between_runs": max(0, int(raw.get("minimum_days_between_runs", policy["minimum_days_between_runs"]))),
        "maximum_runs_per_window": max(0, int(raw.get("maximum_runs_per_window", policy["maximum_runs_per_window"]))),
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


def instance_config(options: dict | None = None) -> dict:
    options = options if options is not None else load_options()
    return {
        "name": os.getenv("LOAD_OPTIMIZER_INSTANCE_1_NAME", "Appliance 1"),
        "power_sensor": os.getenv("LOAD_OPTIMIZER_INSTANCE_1_POWER_SENSOR", "").strip(),
        "energy_sensor": os.getenv("LOAD_OPTIMIZER_INSTANCE_1_ENERGY_SENSOR", "").strip(),
        "program_sensor": os.getenv("LOAD_OPTIMIZER_INSTANCE_1_PROGRAM_SENSOR", "").strip(),
        "state_sensor": os.getenv("LOAD_OPTIMIZER_INSTANCE_1_STATE_SENSOR", "").strip(),
        "active_power_threshold": float(os.getenv("LOAD_OPTIMIZER_INSTANCE_1_ACTIVE_POWER_THRESHOLD", "10")),
        "finish_delay": int(os.getenv("LOAD_OPTIMIZER_INSTANCE_1_FINISH_DELAY", "5")),
        "program_policies": options.get("instance_1_program_policies", []),
        "tariff_entity": str(options.get("tariff_entity", "")).strip(),
        "tariff_timezone": str(options.get("tariff_timezone", "Europe/London")).strip(),
        "tariff_price_unit": str(options.get("tariff_price_unit", "p_per_kwh")),
        "cost_search_hours": int(options.get("cost_search_hours", 24)),
        "cost_candidate_interval": int(options.get("cost_candidate_interval", 5)),
    }


def publish_cost_entities(token: str, prefix: str, name: str, result: dict) -> None:
    status = result.get("status", "error")
    common = {
        "tariff_entity": result.get("tariff_entity"),
        "tariff_periods": result.get("tariff_periods", 0),
        "tariff_start": result.get("tariff_start"),
        "tariff_end": result.get("tariff_end"),
        "reason": result.get("reason"),
    }
    publish_entity(token, f"{prefix}_cost_status", status, {
        "friendly_name": f"{name} Cost Status",
        "icon": "mdi:currency-gbp",
        **common,
    })
    ready = status == "ready"
    values = (
        ("cost_if_started_now", result.get("cost_if_started_now_pence") if ready else "unknown", "p", "mdi:cash-clock"),
        ("cheapest_start", result.get("start").isoformat() if ready else "unknown", None, "mdi:clock-start"),
        ("cheapest_cost", result.get("total_cost_pence") if ready else "unknown", "p", "mdi:cash-check"),
        ("potential_saving", result.get("potential_saving_pence") if ready else "unknown", "p", "mdi:piggy-bank"),
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
        if ready:
            attributes.update({
                "program": result.get("program"),
                "energy_kwh": result.get("energy_kwh"),
                "energy_cost_pence": result.get("energy_cost_pence"),
                "overhead_cost_pence": result.get("overhead_cost_pence"),
                "negative_price_run": result.get("negative_price_run"),
                "candidate_count": result.get("candidate_count"),
            })
            if suffix in {"cheapest_cost", "cheapest_start", "recommended_program"}:
                attributes["cost_breakdown"] = result.get("cost_breakdown", [])
                attributes["breakdown_format"] = "start, end, price_p_per_kwh, energy_kwh, energy_cost_pence"
            if suffix == "cost_if_started_now":
                attributes["cost_breakdown"] = result.get("cost_if_started_now_breakdown", [])
                attributes["breakdown_format"] = "start, end, price_p_per_kwh, energy_kwh, energy_cost_pence"
        publish_entity(token, f"{prefix}_{suffix}", value if value is not None else "unknown", attributes)


def update_instance(token: str, database: dict, config: dict, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    instance = database.setdefault("instances", {}).setdefault("1", {})
    power_entity = source_state(token, config["power_sensor"])
    energy_entity = source_state(token, config["energy_sensor"])
    program_entity = source_state(token, config["program_sensor"])
    device_state_entity = source_state(token, config["state_sensor"])
    power = numeric_state(power_entity)
    energy = numeric_state(energy_entity)
    prefix = "sensor.load_optimizer_1"
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
            last = {
                "program": instance.get("program") or program,
                "runtime_minutes": round((finish - start).total_seconds() / 60, 1),
                "energy_kwh": round(max(0.0, finish_energy - instance["start_energy"]), 4) if finish_energy is not None and instance.get("start_energy") is not None else None,
                "peak_power": instance.get("peak_power", 0),
                "sample_count": len(completed_profile),
                "power_profile": completed_profile,
                "finish": finish.isoformat(),
            }
            instance["last_cycle"] = last
            update_program_model(instance, last)
            instance["runs"] = int(instance.get("runs", 0)) + 1
            for key in ("cycle_start", "start_energy", "peak_power", "samples", "profile", "below_threshold", "finish_candidate", "program"):
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
    summaries = [program_summary(program_name, model) for program_name, model in sorted(models.items())]
    cost_result = {"status": "tariff_not_configured", "tariff_entity": config.get("tariff_entity")}
    if config.get("tariff_entity"):
        tariff_entity = source_state(token, config["tariff_entity"])
        if tariff_entity is None:
            cost_result = {
                "status": "tariff_unavailable",
                "tariff_entity": config["tariff_entity"],
                "reason": "Home Assistant tariff entity could not be read",
            }
        else:
            try:
                periods = tariff_periods_from_entity(
                    tariff_entity,
                    reference_utc=now,
                    timezone_name=config["tariff_timezone"],
                    price_unit=config["tariff_price_unit"],
                )
                cost_result = recommend_cycle(
                    summaries,
                    policies,
                    periods,
                    reference_utc=now,
                    search_hours=config["cost_search_hours"],
                    candidate_interval_minutes=config["cost_candidate_interval"],
                )
                cost_result.update({
                    "tariff_entity": config["tariff_entity"],
                    "tariff_periods": len(periods),
                    "tariff_start": periods[0]["start"].isoformat(),
                    "tariff_end": periods[-1]["end"].isoformat(),
                })
            except (TypeError, ValueError) as error:
                cost_result = {
                    "status": "tariff_invalid",
                    "tariff_entity": config["tariff_entity"],
                    "reason": str(error),
                }
    publish_cost_entities(token, prefix, name, cost_result)
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
    publish_entity(token, f"{prefix}_last_profile", "ready" if profile else "none", {
        "friendly_name": f"{name} Last Power Profile",
        "icon": "mdi:chart-line",
        "program": normalise_program(last.get("program")),
        "runtime_minutes": last.get("runtime_minutes"),
        "sample_count": len(profile),
        "samples": [[sample["offset_seconds"], sample.get("power_w")] for sample in profile],
        "sample_format": ["offset_seconds", "power_w"],
    })
    for suffix, value, attrs in (
        ("last_program", normalise_program(last.get("program")), {"icon": "mdi:format-list-bulleted"}),
        ("last_runtime", last.get("runtime_minutes", 0), {"unit_of_measurement": "min", "device_class": "duration"}),
        ("last_energy", last.get("energy_kwh", 0) if last.get("energy_kwh") is not None else "unknown", {"unit_of_measurement": "kWh", "device_class": "energy"}),
        ("last_finish", last.get("finish", "unknown"), {"device_class": "timestamp"}),
        ("total_runs", instance.get("runs", 0), {"state_class": "total", "icon": "mdi:counter"}),
    ):
        publish_entity(token, f"{prefix}_{suffix}", value, {"friendly_name": f"{name} {suffix.replace('_', ' ').title()}", **attrs})


def publish_status(token: str, instance_count: int) -> None:
    publish_entity(token, STATUS_ENTITY, "running", {
        "friendly_name": "Load Optimizer Status", "icon": "mdi:transmission-tower",
        "version": APP_VERSION, "instances": instance_count,
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
    state = load_state()
    bootstrap_program_models(state)
    config = instance_config()
    save_state(state)
    health_server = run_health_server()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    LOGGER.info("Load Optimizer %s started", APP_VERSION)

    try:
        while not STOP_EVENT.is_set():
            update_instance(token, state, config)
            save_state(state)
            publish_status(token, len(state.get("instances", {})))
            STOP_EVENT.wait(interval)
    finally:
        health_server.shutdown()
        LOGGER.info("Load Optimizer stopped")


if __name__ == "__main__":
    main()
