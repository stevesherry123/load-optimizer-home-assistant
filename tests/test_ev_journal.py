import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('ev_journal', Path(__file__).resolve().parents[1] / 'custom_components/load_optimizer/ev_journal.py')
journal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(journal)


class EVJournalTests(unittest.TestCase):
    def test_only_original_target_can_be_confirmed_stopped(self):
        self.assertTrue(journal.legacy_review({'owned_target': 'switch.original'}, 'switch.original')['can_confirm_stopped'])
        review = journal.legacy_review({'owned_target': 'switch.original'}, 'switch.replacement')
        self.assertEqual(review['original_target'], 'switch.original')
        self.assertFalse(review['can_confirm_stopped'])
        self.assertTrue(journal.legacy_review({'owned_target': None}, 'switch.original')['can_confirm_stopped'])

    def test_targetless_and_unknown_records_never_grant_authority(self):
        checkpoint = {'phase': 'idle', 'owned': False, 'pending': None, 'requires_review': False, 'reason': 'stopped'}
        self.assertEqual(journal.legacy_review(checkpoint, 'switch.original')['reason'], 'legacy_target_unknown')
        for value in ({}, [], {'owned_target': 'sensor.bad'}, {'owned_target': 'switch.bad target'}, {'owned_target': 'switch.original', 'owned': True}):
            with self.subTest(value=value):
                self.assertFalse(journal.legacy_review(value, 'switch.original')['can_confirm_stopped'])
