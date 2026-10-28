"""Execute the shipped chart JavaScript under travelling browser timezones."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
dashboard = yaml.safe_load((ROOT / "homeassistant/dashboards/full/load_optimizer_dashboard.yaml").read_text())

def cards(value):
    if isinstance(value, dict):
        if value.get("type") == "custom:apexcharts-card" and value.get("header", {}).get("title") == "Octopus Prices":
            yield value
        for item in value.values():
            yield from cards(item)
    elif isinstance(value, list):
        for item in value:
            yield from cards(item)

charts = list(cards(dashboard))
assert len(charts) == 2
node = os.environ.get("LOAD_OPTIMIZER_TEST_NODE") or shutil.which("node")
if not node:
    raise RuntimeError("Node.js is required for the dashboard timezone acceptance test")
for zone in ("America/New_York", "Europe/London", "Asia/Tokyo"):
    subprocess.run([node, str(ROOT / "tests/chart_timezone_smoke.js")],
        input=json.dumps(charts), text=True, check=True, env={**os.environ, "TZ": zone})

cost_chart = dashboard["views"][1]["sections"][0]["cards"][0]
assert cost_chart["header"]["title"] == "Dishwasher 1 - Cost Forecast"
subprocess.run([node, str(ROOT / "tests/cost_forecast_smoke.js")],
    input=json.dumps(cost_chart), text=True, check=True)
