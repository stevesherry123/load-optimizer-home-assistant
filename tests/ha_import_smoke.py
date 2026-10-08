"""Run with the declared minimum Home Assistant installed, not with test stubs."""

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from custom_components.load_optimizer.const import PLATFORMS

for module in ("config_flow", "diagnostics", *PLATFORMS):
    importlib.import_module(f"custom_components.load_optimizer.{module}")
print("All integration platform and config-flow imports passed")

import voluptuous as vol
from custom_components.load_optimizer.config_flow import _ev_schema

values = {"tariff_entity": "sensor.rates", "battery_entity": "sensor.battery",
          "battery_capacity_entity": "sensor.capacity", "charge_power_kw": 7.2}
saved = {**values, "target_percent": 85, "target_percent_entity": "sensor.target",
         "connection_status_entity": "sensor.connected", "ready_by": "08:00"}
schema = vol.Schema(_ev_schema(saved))
result = schema(values)
assert result["target_percent"] == 85
for key in ("target_percent_entity", "connection_status_entity", "ready_by"):
    assert key not in result, "Optional references must be clearable, not defaulted back"
for key, value in (("charge_power_kw", 0), ("target_percent", 101), ("charger_efficiency", 0),
                   ("slot_minutes", 4), ("ready_by", "25:00"), ("ready_by", "2026-10-09T08:00:00")):
    try:
        schema({**values, key: value})
    except vol.Invalid:
        pass
    else:
        raise AssertionError("Invalid EV value accepted: " + key)
print("Real Home Assistant EV schema defaults, clearing, numeric and deadline validation passed")
