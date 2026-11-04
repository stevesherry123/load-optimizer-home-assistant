"""Regression tests for full-report, fail-closed validation orchestration."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("validation_runner", ROOT / "dev/validate.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ValidationRunnerTests(unittest.TestCase):
    def test_source_identity_tracks_edits_without_disclosing_source_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                subprocess.run(["git", *args], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            git("init")
            (root / "example.py").write_text("PRIVATE_FIXTURE_VALUE = 1\n")
            (root / ".gitignore").write_text(".env\n")
            git("add", ".")
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "Fixture")
            clean = runner.source_identity(root=root)
            self.assertTrue(clean["available"])
            self.assertFalse(clean["worktree_dirty"])
            self.assertNotIn("PRIVATE_FIXTURE_VALUE", json.dumps(clean))
            (root / ".env").write_text("PRIVATE_IGNORED_FIXTURE\n")
            self.assertEqual(runner.source_identity(root=root), clean)
            # Custom report outputs are not source changes, even outside .local.
            output = root / "reports"
            output.mkdir()
            (output / "unit.log").write_text("Synthetic log\n")
            self.assertEqual(runner.source_identity(root=root, exclude=output), clean)
            (root / "example.py").write_text("PRIVATE_FIXTURE_VALUE = 2\n")
            changed = runner.source_identity(root=root, exclude=output)
            self.assertTrue(changed["worktree_dirty"])
            self.assertNotEqual(changed["fingerprint_sha256"], clean["fingerprint_sha256"])
            self.assertEqual(changed["commit"], clean["commit"])

    def test_changed_source_invalidates_an_otherwise_green_run(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            output.mkdir()
            def checks(*args):
                return [{"name": "fixture", "passed": True, "returncode": 0, "seconds": 0, "log": "fixture.log"}]
            with patch.object(sys, "argv", ["validate.py", "--output", str(output)]), \
                 patch.object(runner, "preflight", return_value={"python": "3.14"}), \
                 patch.object(runner, "run_checks", side_effect=checks), \
                 patch.object(runner, "source_identity", side_effect=[
                     {"available": True, "commit": "abc", "worktree_dirty": False, "fingerprint_sha256": "one"},
                     {"available": True, "commit": "abc", "worktree_dirty": True, "fingerprint_sha256": "two"},
                 ]):
                self.assertEqual(runner.main(), 1)
            report = json.loads((output / "results.json").read_text())
            self.assertFalse(report["source"]["unchanged"])
            self.assertIn("NO — rerun validation", (output / "summary.md").read_text())

    def test_every_acceptance_script_is_discovered_once(self):
        items = runner.checks(["ha"])
        expected = {p.stem for p in (ROOT / "tests").glob("ha_*_smoke.py")
                    if p.name != "ha_chart_browser_smoke.py"}
        self.assertEqual({name for name, _ in items}, expected)
        self.assertEqual(len(items), len(expected))
        self.assertEqual(items[0][0], "ha_import_smoke")
        self.assertTrue(all(command[0] == sys.executable for _, command in items))

    def test_browser_harness_has_an_explicit_suite(self):
        name, command = runner.checks(["browser"])[0]
        self.assertEqual(name, "ha_chart_browser_smoke")
        self.assertEqual(Path(command[-1]).name, "ha_chart_browser_smoke.py")

    def test_failed_check_does_not_hide_later_pass_or_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results"
            items = [("first", [sys.executable, "-c", "raise SystemExit(7)"]),
                     ("second", [sys.executable, "-c", "print('passed after failure')"]),
                     ("third", [sys.executable, "-c", "raise SystemExit(3)"])]
            results = runner.run_checks(items, output, 10)
            self.assertEqual([r["returncode"] for r in results], [7, 0, 3])
            self.assertTrue(any(not r["passed"] for r in results))
            self.assertIn("passed after failure", (output / "second.log").read_text())
            self.assertIn("| third | FAIL |", runner.markdown(results))

    def test_timeout_is_failure_and_later_check_still_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = [subprocess.TimeoutExpired("fixture", 1), subprocess.CompletedProcess([], 0)]
            with patch.object(runner.subprocess, "run", side_effect=calls):
                result = runner.run_checks([("slow", []), ("next", [])], Path(directory) / "logs", 1)
            self.assertEqual([r["returncode"] for r in result], [124, 0])

    def test_preflight_rejects_old_python_even_with_correct_packages(self):
        versions = dict(line.split("==") for line in runner.REQUIREMENTS.read_text().splitlines())
        with patch.object(runner.metadata, "version", side_effect=versions.__getitem__), \
             patch.object(runner.sys, "version_info", (3, 12)):
            with self.assertRaisesRegex(ValueError, "Python 3.14"):
                runner.preflight()

    def test_preflight_rejects_missing_or_wrong_dependencies(self):
        def missing(name):
            if name == "homeassistant":
                raise runner.metadata.PackageNotFoundError(name)
            return "wrong"
        with patch.object(runner.metadata, "version", side_effect=missing), \
             patch.object(runner.sys, "version_info", (3, 14)):
            with self.assertRaisesRegex(ValueError, "homeassistant: expected .* found missing"):
                runner.preflight()

    def test_main_failure_and_summary_are_not_replaced_by_later_success(self):
        results = [{"name": "bad", "returncode": 1, "passed": False, "seconds": 0, "log": "bad.log"},
                   {"name": "good", "returncode": 0, "passed": True, "seconds": 0, "log": "good.log"}]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            output.mkdir()
            with patch.object(sys, "argv", ["validate.py", "--output", str(output)]), \
                 patch.object(runner, "preflight", return_value={"python": "3.14"}), \
                 patch.object(runner, "run_checks", return_value=results):
                self.assertEqual(runner.main(), 1)
            self.assertEqual(json.loads((output / "results.json").read_text())["checks"], results)

    def test_workflow_deduplicates_beta_pushes_without_skipping_pr_validation(self):
        workflow = yaml.load((ROOT / ".github/workflows/validate.yaml").read_text(), Loader=yaml.BaseLoader)
        self.assertEqual(workflow["on"]["push"]["branches"], ["main"])
        self.assertIn("pull_request", workflow["on"])
        self.assertIn("workflow_dispatch", workflow["on"])
        self.assertIn("schedule", workflow["on"])
        steps = workflow["jobs"]["minimum_ha"]["steps"]
        self.assertTrue(any("dev/validate.py --suite ha" in s.get("run", "") for s in steps))
        summary = next(s for s in steps if s.get("name") == "Publish acceptance summary")
        self.assertEqual(summary["if"], "always()")
        self.assertFalse(any("continue-on-error" in s for s in steps))

    def test_minimum_ha_matches_shared_requirements(self):
        requirements = dict(line.split("==") for line in runner.REQUIREMENTS.read_text().splitlines())
        minimum = json.loads((ROOT / "hacs.json").read_text())["homeassistant"]
        self.assertEqual(requirements["homeassistant"], minimum)

    def test_bootstrap_dependency_drift_fails_before_acceptance(self):
        versions = dict(line.split("==") for line in runner.REQUIREMENTS.read_text().splitlines())
        with patch.object(runner.metadata, "version", side_effect=versions.__getitem__), \
             patch.object(runner.sys, "version_info", (3, 14)), \
             patch.object(runner, "ha_runtime_requirements", return_value=["pyotp==99.0.0"]):
            with self.assertRaisesRegex(ValueError, "HA bootstrap requires pyotp==99.0.0"):
                runner.preflight()

    def test_isolated_bootstrap_never_installs_dependencies(self):
        for path in (ROOT / "tests").glob("ha_*_smoke.py"):
            source = path.read_text()
            if "hass = HomeAssistant(" in source:
                self.assertIn("hass.config.skip_pip = True", source, path.name)
