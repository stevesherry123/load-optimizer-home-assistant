import json
import tempfile
import unittest
from pathlib import Path

from load_optimizer.app.main import load_state, save_state


class StateStorageTests(unittest.TestCase):
    def test_missing_state_returns_empty_versioned_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            self.assertEqual(
                load_state(path),
                {"schema_version": 1, "instances": {}},
            )

    def test_state_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            expected = {
                "schema_version": 1,
                "instances": {"1": {"name": "Dishwasher 1"}},
            }
            save_state(expected, path)
            self.assertEqual(json.loads(path.read_text()), expected)
            self.assertEqual(load_state(path), expected)


if __name__ == "__main__":
    unittest.main()
