import logging
import sys
import unittest
from pathlib import Path

INTEGRATION_ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "load_optimizer"
sys.path.insert(0, str(INTEGRATION_ROOT))

from legacy.observability import EventEngine


class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.engine = EventEngine(logging.getLogger("test_observability"), history_size=10)

    def test_snapshot_contains_stable_event_and_context(self):
        self.engine.warning("LO-TEST-WARNING", "Something needs attention", instance_id="2")
        snapshot = self.engine.snapshot()
        self.assertEqual(snapshot["event_counts"]["warning"], 1)
        self.assertEqual(snapshot["recent_events"][0]["event"], "LO-TEST-WARNING")
        self.assertEqual(snapshot["recent_events"][0]["context"]["instance_id"], "2")

    def test_sensitive_context_is_redacted_recursively(self):
        self.engine.error("LO-TEST-SECRET", "Credentials must not leak", token="abc", request={"Authorization": "Bearer private", "entity": "sensor.safe"})
        context = self.engine.snapshot()["last_error"]["context"]
        self.assertEqual(context["token"], "<redacted>")
        self.assertEqual(context["request"]["Authorization"], "<redacted>")
        self.assertEqual(context["request"]["entity"], "sensor.safe")

    def test_debug_events_are_counted_but_not_published_in_history(self):
        self.engine.debug("LO-TEST-DEBUG", "Verbose detail", sample=list(range(100)))
        snapshot = self.engine.snapshot()
        self.assertEqual(snapshot["event_counts"]["debug"], 1)
        self.assertEqual(snapshot["recent_events"], [])

    def test_history_has_a_safe_upper_bound(self):
        engine = EventEngine(logging.getLogger("bounded"), history_size=10)
        for index in range(15):
            engine.info("LO-TEST-INFO", "bounded", index=index)
        events = engine.snapshot()["recent_events"]
        self.assertEqual(len(events), 10)
        self.assertEqual(events[0]["context"]["index"], 5)

    def test_credentials_in_messages_and_exception_values_are_redacted(self):
        credentials = ["Bearer " + "test-credential-value", "eyJ" + "fake.fake.signature",
                       "https://user:" + "test-secret@host/path", "token=" + "test-secret",
                       "sk-proj-" + "x" * 32, "ghp_" + "x" * 32]
        for credential in credentials:
            with self.subTest(credential=credential):
                with self.assertLogs("test_observability", logging.ERROR) as captured:
                    self.engine.error("LO-REDACTION", credential, error=credential)
                self.assertNotIn(credential, str(captured.output))
                self.assertNotIn(credential, str(self.engine.snapshot()["last_error"]))

    def test_recursive_context_is_bounded(self):
        value = {}
        value["self"] = value
        self.engine.info("LO-BOUNDED", "Recursive input", details=value)
        self.assertIn("<truncated>", str(self.engine.snapshot()))
