import logging
import unittest

from load_optimizer.app.observability import EventEngine


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
