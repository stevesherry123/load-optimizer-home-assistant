"""Runtime entry point for the Load Optimizer Home Assistant App."""

from __future__ import annotations

import json
import logging
import os
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

APP_VERSION = "0.1.0"
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


def publish_status(token: str, instance_count: int) -> None:
    payload = json.dumps(
        {
            "state": "running",
            "attributes": {
                "friendly_name": "Load Optimizer Status",
                "icon": "mdi:transmission-tower",
                "version": APP_VERSION,
                "instances": instance_count,
            },
        }
    ).encode("utf-8")
    request = Request(
        f"{API_BASE_URL}/states/{STATUS_ENTITY}",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=10) as response:
            response.read()
    except (HTTPError, URLError, TimeoutError) as error:
        LOGGER.warning("Could not publish Home Assistant status: %s", error)


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
    save_state(state)
    health_server = run_health_server()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    LOGGER.info("Load Optimizer %s started", APP_VERSION)

    try:
        while not STOP_EVENT.is_set():
            publish_status(token, len(state.get("instances", {})))
            STOP_EVENT.wait(interval)
    finally:
        health_server.shutdown()
        LOGGER.info("Load Optimizer stopped")


if __name__ == "__main__":
    main()
