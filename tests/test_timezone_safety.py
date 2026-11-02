"""Prevent the HACS-reported synchronous timezone lookup from returning."""

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/load_optimizer"


class TimezoneSafetyTests(unittest.TestCase):
    def test_price_cap_reuses_supplied_timezone(self):
        tree = ast.parse((ROOT / "price_cap.py").read_text())
        method = next(n for n in ast.walk(tree) if isinstance(n,ast.AsyncFunctionDef) and n.name=="async_status")
        self.assertIn("local_timezone", [arg.arg for arg in method.args.kwonlyargs])
        self.assertNotIn("ZoneInfo", (ROOT / "price_cap.py").read_text())
        conversions = [n for n in ast.walk(method) if isinstance(n,ast.Call)
                       and isinstance(n.func,ast.Attribute) and n.func.attr=="astimezone"
                       and n.args and isinstance(n.args[0],ast.Name) and n.args[0].id=="local_timezone"]
        self.assertEqual(len(conversions),2)

    def test_entry_setup_resolves_timezone_once_before_refresh(self):
        tree = ast.parse((ROOT / "__init__.py").read_text())
        setup = next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=="async_setup_entry")
        resolves = [n for n in ast.walk(setup) if isinstance(n,ast.Await) and isinstance(n.value,ast.Call)
                    and isinstance(n.value.func,ast.Attribute) and n.value.func.attr=="async_get_time_zone"]
        self.assertEqual(len(resolves),1)
        constructor = next(n for n in ast.walk(setup) if isinstance(n,ast.Call)
                           and isinstance(n.func,ast.Name) and n.func.id=="LoadOptimizerCoordinator")
        self.assertLess(resolves[0].lineno,constructor.lineno)
        self.assertTrue(any(k.arg=="local_timezone" for k in constructor.keywords))

    def test_native_scheduler_uses_home_assistants_resolved_zone(self):
        self.assertNotIn("ZoneInfo", (ROOT / "orchestration.py").read_text())
