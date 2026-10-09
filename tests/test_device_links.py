"""Exercise actual compatibility-helper code without Home Assistant stubs."""

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class DeviceLinkTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / "custom_components/load_optimizer/entity.py"
        function = next(node for node in ast.parse(source.read_text()).body
                        if isinstance(node, ast.FunctionDef) and node.name == "registered_hub_link")
        self.registry = SimpleNamespace()
        namespace = {"DOMAIN": "load_optimizer", "HomeAssistant": object,
                     "ConfigEntry": object, "DeviceInfo": dict,
                     "dr": SimpleNamespace(async_get=lambda hass: self.registry)}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "<device-link>", "exec"), namespace)
        self.link = namespace[function.name]
        self.entry = SimpleNamespace(entry_id="entry")

    def test_modern_registry_scopes_lookup_and_uses_id(self):
        self.registry.async_get_device_by_identifier = Mock(return_value=SimpleNamespace(id="hub"))
        self.assertEqual(self.link(None, self.entry), {"via_device_id": "hub"})
        self.registry.async_get_device_by_identifier.assert_called_once_with(("load_optimizer", "entry"), "entry")

    def test_modern_missing_hub_does_not_link(self):
        self.registry.async_get_device_by_identifier = Mock(return_value=None)
        self.assertEqual(self.link(None, self.entry), {})

    def test_older_registry_links_only_existing_owned_hub(self):
        self.registry.async_get_device = Mock(return_value=SimpleNamespace(config_entries={"entry"}))
        self.assertEqual(self.link(None, self.entry), {"via_device": ("load_optimizer", "entry")})
        self.registry.async_get_device.assert_called_once_with(identifiers={("load_optimizer", "entry")})

    def test_older_registry_rejects_other_entry_hub(self):
        self.registry.async_get_device = Mock(return_value=SimpleNamespace(config_entries={"other"}))
        self.assertEqual(self.link(None, self.entry), {})

    def test_older_missing_hub_does_not_link(self):
        self.registry.async_get_device = Mock(return_value=None)
        self.assertEqual(self.link(None, self.entry), {})
