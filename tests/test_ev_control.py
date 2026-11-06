"""Control lifecycle acceptance without charger commands or Home Assistant."""

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "custom_components/load_optimizer/ev_control.py"
SPEC = importlib.util.spec_from_file_location("ev_control", SOURCE)
control = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(control)


class EVControlTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 4, 21, tzinfo=timezone.utc)
        self.session = control.EVControlSession()

    def tick(self, seconds=0, **kwargs):
        now = self.now + timedelta(seconds=seconds)
        return self.session.evaluate(**{
            "now": now, "observed_at": now, "enabled": True, "desired": True,
            "connected": True, "charging": False, "telemetry_fresh": True, **kwargs,
        })

    def test_disabled_disconnected_and_no_plan_do_not_start(self):
        for overrides in ({"enabled": False}, {"connected": False}, {"connected": None},
                          {"desired": False}, {"telemetry_fresh": False}, {"charging": None},
                          {"charging": "unknown"}, {"enabled": "on"}, {"desired": "on"}):
            self.assertIsNone(self.tick(**overrides))
        self.assertFalse(self.session.owned)

    def test_start_reserved_once_and_requires_new_physical_observation(self):
        command = self.tick()
        self.assertEqual(command["action"], "start")
        self.assertIsNone(self.tick(1))
        self.assertIsNone(self.tick(2, charging=True, observed_at=self.now))
        self.assertEqual(self.session.phase, "starting")
        self.assertIsNone(self.tick(3, charging=True))
        self.assertEqual(self.session.phase, "charging")
        self.assertIsNone(self.tick(4, charging=True))

    def test_stop_reserved_once_after_interval_and_confirmed(self):
        self.tick()
        self.tick(1, charging=True)
        command = self.tick(2, charging=True, desired=False)
        self.assertEqual(command["action"], "stop")
        self.assertIsNone(self.tick(3, charging=True, desired=False))
        self.assertIsNone(self.tick(4, charging=False, desired=False))
        self.assertFalse(self.session.owned)
        self.assertEqual(self.session.phase, "idle")

    def test_permission_removed_during_start_stops_after_confirmation(self):
        self.tick()
        self.assertIsNone(self.tick(1, enabled=False))
        self.assertEqual(self.tick(2, enabled=False, charging=True)["action"], "stop")

    def test_external_charging_is_never_claimed_or_stopped(self):
        self.assertIsNone(self.tick(charging=True, enabled=False, desired=False))
        self.assertFalse(self.session.owned)
        self.assertEqual(self.session.reason, "external_charging_not_owned")

    def test_external_stop_blocks_automatic_restart(self):
        self.tick()
        self.tick(1, charging=True)
        self.assertIsNone(self.tick(2))
        self.assertEqual(self.session.reason, "charging_stopped_externally")
        self.assertIsNone(self.tick(3))

    def test_timeout_and_failed_dispatch_block_retries(self):
        for failure in (False, True):
            self.session = control.EVControlSession()
            command = self.tick()
            if failure:
                self.session.dispatch_failed(command["id"])
            self.assertIsNone(self.tick(60))
            self.assertEqual(self.session.phase, "blocked")
            self.assertIsNone(self.tick(120, charging=True))

    def test_stale_callback_cannot_fail_new_command(self):
        self.tick()
        self.session.dispatch_failed("old-command")
        self.assertEqual(self.session.phase, "starting")

    def test_restart_quarantines_saved_authority_without_replaying(self):
        self.tick()
        saved = json.loads(json.dumps(self.session.checkpoint()))
        self.session = control.EVControlSession.restored(saved)
        self.assertIsNone(self.tick(1, charging=True))
        self.assertFalse(self.session.reconcile_stopped(charging=True, telemetry_fresh=True))
        self.assertFalse(self.session.reconcile_stopped(charging=False, telemetry_fresh=False))
        self.assertTrue(self.session.reconcile_stopped(charging=False, telemetry_fresh=True))
        self.assertEqual(self.tick(2)["action"], "start")

    def test_stale_future_or_missing_observation_never_starts(self):
        for observed_at in (None, self.now - timedelta(seconds=61),
                            self.now + timedelta(seconds=1), self.now.replace(tzinfo=None)):
            self.assertIsNone(self.tick(observed_at=observed_at))

    def test_owned_charge_stops_when_plan_or_connection_is_lost(self):
        for changes in ({"desired": False}, {"connected": None}, {"enabled": False}):
            self.session = control.EVControlSession()
            self.tick()
            self.tick(1, charging=True)
            self.assertEqual(self.tick(2, charging=True, **changes)["action"], "stop")

    def test_invalid_control_time_and_timeout_are_rejected(self):
        with self.assertRaises(ValueError):
            self.tick(now=self.now.replace(tzinfo=None))
        for timeout in (0, 601, True, 1.5):
            with self.assertRaises(ValueError):
                control.EVControlSession(confirmation_seconds=timeout)
