"""Run with the declared minimum Home Assistant installed, not with test stubs."""

import importlib
import sys
from pathlib import Path
import homeassistant  # Initialise the core's schema compatibility layer first.

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from custom_components.load_optimizer.const import PLATFORMS

for module in ("config_flow", "diagnostics", *PLATFORMS):
    importlib.import_module(f"custom_components.load_optimizer.{module}")
print("All integration platform and config-flow imports passed")

import voluptuous as vol
from custom_components.load_optimizer.config_flow import _ev_schema, _ev_input_errors
from homeassistant.helpers.config_validation import custom_serializer
try:
    from probatio import to_field_list as convert
except ImportError:
    from voluptuous_serialize import convert

values = {"tariff_entity": "sensor.rates", "battery_entity": "sensor.battery",
          "battery_capacity_entity": "sensor.capacity", "charge_power_kw": 7.2}
saved = {**values, "target_percent": 85, "target_percent_entity": "sensor.target",
         "connection_status_entity": "sensor.connected", "ready_by": "08:00"}
schema = vol.Schema(_ev_schema(saved))
result = schema(values)
assert result["target_percent"] == 85
for key in ("target_percent_entity", "connection_status_entity", "ready_by"):
    assert key not in result, "Optional references must be clearable, not defaulted back"
serialized = convert(schema, custom_serializer=custom_serializer)
assert next(field for field in serialized if field["name"] == "ready_by")["type"] == "string"
for key, value in (("charge_power_kw", 0), ("target_percent", 101), ("charger_efficiency", 0),
                   ("slot_minutes", 4)):
    try:
        schema({**values, key: value})
    except vol.Invalid:
        pass
    else:
        raise AssertionError("Invalid EV value accepted: " + key)
for key, value in (("ready_by", "25:00"), ("ready_by", "2026-10-09T08:00:00"),
                   ("tariff_timezone", "Invalid/Timezone"), ("slot_minutes", 30.5),
                   ("charge_power_kw", float("nan")), ("target_percent", float("inf")),
                   ("charger_efficiency", True)):
    assert key in _ev_input_errors({**values, key: value}), (key, value)
assert not _ev_input_errors({**values, "ready_by": "08:00"})
assert not _ev_input_errors({**values, "ready_by": ""})
print("Real Home Assistant EV schema defaults, clearing, numeric and deadline validation passed")

import asyncio
from types import SimpleNamespace
from custom_components.load_optimizer.config_flow import LoadOptimizerOptionsFlow


async def verify_options_display():
    values = {"cost_search_hours": 18, "cost_forecast_hours": 48,
              "cost_forecast_interval": 30, "cost_candidate_interval": 5}
    view = SimpleNamespace(
        _existing=values, _appliance_save_errors=lambda: {},
        async_show_form=lambda **kwargs: kwargs,
        _dishwasher_existing={"bosch_power_switch": "switch.migrated_dishwasher",
                              "bosch_device_id": "migrated-device"},
    )
    result = await LoadOptimizerOptionsFlow.async_step_optimisation(view)
    fields = convert(result["data_schema"], custom_serializer=custom_serializer)
    defaults = result["data_schema"]({})
    for name, value in values.items():
        field = next(item for item in fields if item["name"] == name)
        assert field["selector"]["number"]["mode"] == "box", field
        assert defaults[name] == value, defaults
        for invalid in (0, 1000):
            try:
                result["data_schema"]({name: invalid})
            except vol.Invalid:
                pass
            else:
                raise AssertionError("Out-of-range optimisation value accepted: " + name)
    result = await LoadOptimizerOptionsFlow.async_step_dishwasher_control(view)
    convert(result["data_schema"], custom_serializer=custom_serializer)
    defaults = result["data_schema"]({})
    assert defaults["bosch_power_switch"] == "switch.migrated_dishwasher"
    assert defaults["bosch_device_id"] == "migrated-device"
    assert view._existing == values


asyncio.run(verify_options_display())
print("Options display: visible numeric values and migrated controller defaults passed")
