"""Public package checks and execution of the single learned-hub guard."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components/load_optimizer"


class PublicationTests(unittest.TestCase):
    def test_public_hacs_metadata_and_integration_are_complete(self):
        metadata = json.loads((ROOT / "hacs.json").read_text())
        manifest = json.loads((INTEGRATION / "manifest.json").read_text())
        self.assertEqual(metadata["country"], "GB")
        self.assertEqual(metadata["homeassistant"], "2024.12.0")
        self.assertTrue(metadata["hide_default_branch"])
        self.assertEqual([p.name for p in (ROOT / "custom_components").iterdir()
                          if p.is_dir() and not p.name.startswith("__")], ["load_optimizer"])
        for key in ("domain", "name", "version", "codeowners", "documentation", "issue_tracker"):
            self.assertTrue(manifest[key])
        self.assertTrue(manifest["config_flow"])
        self.assertIn("MIT License", (ROOT / "LICENSE").read_text())

    def test_validation_has_no_ignored_hacs_checks(self):
        workflow = (ROOT / ".github/workflows/validate.yaml").read_text()
        self.assertRegex(workflow, r"hacs/action@[a-f0-9]{40}")
        self.assertRegex(workflow, r"home-assistant/actions/hassfest@[a-f0-9]{40}")
        self.assertIn("contents: read", workflow)
        self.assertIn("Security and credential scan", workflow)
        self.assertNotIn("ignore:", workflow)
        self.assertNotIn("continue-on-error", workflow)
        self.assertIn('homeassistant==2024.12.0', workflow)


class LearnedHubTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tree = ast.parse((INTEGRATION / "config_flow.py").read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                   and n.name == "LoadOptimizerConfigFlow")
        method = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef)
                      and n.name == "async_step_learned_appliance")
        namespace = {"Any": object, "CONF_LOAD_TYPE": "load_type", "CONF_NAME": "name",
                     "LOAD_TYPE_LEARNED_APPLIANCE": "learned_appliance"}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "<config-flow-guard>", "exec"), namespace)
        self.method = namespace[method.name]
        self.flow = SimpleNamespace(
            _name="New name", _async_current_entries=lambda: [],
            async_abort=Mock(side_effect=lambda **kw: kw),
            async_set_unique_id=AsyncMock(), _abort_if_unique_id_configured=Mock(),
            async_create_entry=Mock(side_effect=lambda **kw: kw),
        )

    async def test_existing_learned_hub_blocks_even_a_different_title(self):
        self.flow._async_current_entries = lambda: [SimpleNamespace(data={"load_type": "learned_appliance"})]
        result = await self.method(self.flow, {"instances_yaml": "[]"})
        self.assertEqual(result, {"reason": "learned_appliance_already_configured"})
        self.flow.async_create_entry.assert_not_called()
        self.flow.async_set_unique_id.assert_not_called()

    async def test_ev_does_not_block_new_learned_hub(self):
        self.flow._async_current_entries = lambda: [SimpleNamespace(data={"load_type": "ev_charging"})]
        result = await self.method(self.flow, {"instances_yaml": "[]"})
        self.assertEqual(result["title"], "New name")
        self.flow.async_set_unique_id.assert_awaited_once_with("learned_appliance")
        self.assertEqual(result["data"]["load_type"], "learned_appliance")

    async def test_guard_runs_before_showing_the_form(self):
        self.flow._async_current_entries = lambda: [SimpleNamespace(data={"load_type": "learned_appliance"})]
        result = await self.method(self.flow, None)
        self.assertEqual(result["reason"], "learned_appliance_already_configured")
