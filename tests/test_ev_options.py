"""Execute the actual EV options methods without importing Home Assistant."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1] / "custom_components/load_optimizer"
spec = importlib.util.spec_from_file_location("ev_options_constants", ROOT / "const.py")
constants = importlib.util.module_from_spec(spec)
spec.loader.exec_module(constants)


class FlowBase:
    def async_show_menu(self, **kwargs):
        return {"type": "menu", **kwargs}

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_abort(self, **kwargs):
        return {"type": "abort", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}


class EVOptionsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tree = ast.parse((ROOT / "config_flow.py").read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                   and n.name == "LoadOptimizerOptionsFlow")
        namespace = {k: v for k, v in vars(constants).items() if k.isupper()}
        namespace.update({"config_entries": SimpleNamespace(OptionsFlow=FlowBase),
                          "vol": SimpleNamespace(Schema=lambda value: value),
                          "_ev_schema": Mock(return_value={"ev": "schema"}),
                          "_price_cap_schema": Mock(return_value={"region": "schema"})})
        exec(compile(ast.Module(body=[cls], type_ignores=[]), "<ev-options>", "exec"), namespace)
        self.namespace = namespace
        self.flow = namespace[cls.name]()
        self.data = {"load_type": "ev_charging", "name": "Car", "battery_entity": "sensor.old",
                     "target_percent_entity": "sensor.target", "ready_by": "08:00"}
        self.options = {"target_percent": 85, "price_cap_region": "Merseyside and Northern Wales",
                        "connection_status_entity": "sensor.connected"}
        self.flow.config_entry = SimpleNamespace(data=self.data, options=self.options, entry_id="unchanged")

    async def test_ev_gets_only_ev_and_benchmark_menu(self):
        result = await self.flow.async_step_init()
        self.assertEqual(result["menu_options"], ["ev", "price_cap"])

    async def test_learned_appliance_menu_is_unchanged(self):
        self.data["load_type"] = "learned_appliance"
        result = await self.flow.async_step_init()
        self.assertEqual(result["menu_options"], ["appliances_tariff", "optimisation", "publishing",
                                                 "price_cap", "dishwasher_control"])

    async def test_unsupported_type_still_aborts(self):
        self.data["load_type"] = "future_type"
        self.assertEqual((await self.flow.async_step_init())["reason"], "not_supported")

    async def test_form_prefills_merged_settings_with_options_taking_precedence(self):
        result = await self.flow.async_step_ev()
        self.assertEqual(result["step_id"], "ev")
        self.namespace["_ev_schema"].assert_called_once_with({**self.data, **self.options})

    async def test_save_preserves_unrelated_settings_and_identity(self):
        result = await self.flow.async_step_ev({"battery_entity": "sensor.new", "target_percent": 90,
                                                "target_percent_entity": "sensor.target",
                                                "connection_status_entity": "sensor.connected", "ready_by": ""})
        self.assertEqual(result["data"]["price_cap_region"], self.options["price_cap_region"])
        self.assertEqual(result["data"]["target_percent"], 90)
        self.assertEqual(self.flow.config_entry.entry_id, "unchanged")
        self.assertEqual(self.data["battery_entity"], "sensor.old")
        self.assertEqual(self.options["target_percent"], 85)

    async def test_omitted_optional_references_override_old_data_and_options(self):
        result = await self.flow.async_step_ev({"charge_power_kw": 7.2})
        merged = {**self.data, **result["data"]}
        for key in ("target_percent_entity", "connection_status_entity", "ready_by"):
            self.assertEqual(merged[key], "")
        self.assertEqual(merged["target_percent"], 85)

    async def test_benchmark_edit_preserves_ev_options(self):
        result = await self.flow.async_step_price_cap({"price_cap_region": "North Western England"})
        self.assertEqual(result["data"]["target_percent"], 85)
        self.assertEqual(result["data"]["connection_status_entity"], "sensor.connected")
