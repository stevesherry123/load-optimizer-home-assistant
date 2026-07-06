"""Runtime entry point for the Load Optimizer Home Assistant App."""

from __future__ import annotations

import json
import logging
import os
import signal
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

APP_VERSION = "0.2.0"
API_BASE_URL = "http://supervisor/core/api"
DATA_PATH = Path("/data/load_optimizer.json")
STATUS_ENTITY = "sensor.load_optimizer_status"

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


def instance_config() -> dict:
    return {
        "name": os.getenv("LOAD_OPTIMIZER_INSTANCE_1_NAME", "Appliance 1"),
        "power_sensor": os.getenv("LOAD_OPTIMIZER_INSTANCE_1_POWER_SENSOR", "").strip(),
        "energy_sensor": os.getenv("LOAD_OPTIMIZER_INSTANCE_1_ENERGY_SENSOR", "").strip(),
        "program_sensor": os.getenv("LOAD_OPTIMIZER_INSTANCE_1_PROGRAM_SENSOR", "").strip(),
        "state_sensor": os.getenv("LOAD_OPTIMIZER_INSTANCE_1_STATE_SENSOR", "").strip(),
        "active_power_threshold": float(os.getenv("LOAD_OPTIMIZER_INSTANCE_1_ACTIVE_POWER_THRESHOLD", "10")),
        "finish_delay": int(os.getenv("LOAD_OPTIMIZER_INSTANCE_1_FINISH_DELAY", "5")),
    }


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
    program = program_entity["state"] if program_entity else "unknown"
    publish_entity(token, f"{prefix}_program", program, {
        "friendly_name": f"{name} Program", "icon": "mdi:format-list-bulleted", "source_entity": config["program_sensor"] or None,
    })

    active = power is not None and power >= config["active_power_threshold"]
    if active:
        if not instance.get("cycle_start"):
            instance.update(cycle_start=now.isoformat(), start_energy=energy, peak_power=power, samples=0, below_threshold=0)
        instance["samples"] = int(instance.get("samples", 0)) + 1
        instance["peak_power"] = max(float(instance.get("peak_power", 0)), power)
        instance["below_threshold"] = 0
    elif instance.get("cycle_start"):
        instance["below_threshold"] = int(instance.get("below_threshold", 0)) + 1
        if instance["below_threshold"] >= config["finish_delay"]:
            start = datetime.fromisoformat(instance["cycle_start"])
            last = {
                "program": instance.get("program") or program,
                "runtime_minutes": round((now - start).total_seconds() / 60, 1),
                "energy_kwh": round(max(0.0, energy - instance["start_energy"]), 4) if energy is not None and instance.get("start_energy") is not None else None,
                "peak_power": instance.get("peak_power", 0), "finish": now.isoformat(),
            }
            instance["last_cycle"] = last
            instance["runs"] = int(instance.get("runs", 0)) + 1
            for key in ("cycle_start", "start_energy", "peak_power", "samples", "below_threshold", "program"):
                instance.pop(key, None)
    if instance.get("cycle_start") and program not in ("unknown", "unavailable", ""):
        instance["program"] = program

    cycle_state = "running" if instance.get("cycle_start") else "idle"
    publish_entity(token, f"{prefix}_cycle_state", cycle_state, {
        "friendly_name": f"{name} Cycle State", "icon": "mdi:dishwasher" if "dishwasher" in name.lower() else "mdi:lightning-bolt",
        "source_state": device_state_entity["state"] if device_state_entity else None,
    })
    publish_entity(token, f"{prefix}_sample_count", instance.get("samples", 0), {
        "friendly_name": f"{name} Cycle Samples", "state_class": "measurement", "icon": "mdi:counter",
    })
    publish_entity(token, f"{prefix}_peak_power", instance.get("peak_power", instance.get("last_cycle", {}).get("peak_power", 0)), {
        "friendly_name": f"{name} Peak Power", "device_class": "power", "unit_of_measurement": "W", "state_class": "measurement",
    })
    last = instance.get("last_cycle", {})
    for suffix, value, attrs in (
        ("last_program", last.get("program", "unknown"), {"icon": "mdi:format-list-bulleted"}),
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
