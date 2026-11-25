"""Regression checks for a trial build being replaced through routine updates."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'dev/check_owner_channel.py'
spec = importlib.util.spec_from_file_location('owner_channel', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class OwnerChannelTests(unittest.TestCase):
    def setUp(self):
        self.tag = 'v1.7.0-beta.12'
        self.snapshot = {
            'ha_state': 'RUNNING', 'entries_loaded': True, 'provider': 'marketplace',
            'manifest_version': '1.7.0-beta.12',
            'repository': {'id': module.REPOSITORY_ID, 'full_name': module.REPOSITORY,
                'beta': True, 'installed': True, 'installed_version': self.tag,
                'available_version': self.tag, 'version_or_commit': 'version',
                'pending_upgrade': False, 'update_entity_id': 'update.synthetic'},
            'update': {'entity_id': 'update.synthetic', 'state': 'off', 'attributes': {
                'installed_version': self.tag, 'latest_version': self.tag, 'in_progress': False}},
        }

    def test_versioned_beta_channel_matches(self):
        self.assertEqual(module.validate_snapshot(self.tag, self.snapshot), [])

    def test_raw_commit_install_and_stable_channel_reproduce_the_incident(self):
        self.snapshot['repository'].update(beta=False, installed_version='a' * 40, available_version='v1.5.9')
        self.snapshot['update'].update(state='on', attributes={
            'installed_version': 'a' * 40, 'latest_version': 'v1.5.9', 'in_progress': False})
        self.assertGreaterEqual(len(module.validate_snapshot(self.tag, self.snapshot)), 5)
        self.assertTrue(module.validate_snapshot('a' * 40, self.snapshot))

    def test_channel_mismatch_fails_even_if_update_is_off(self):
        self.snapshot['repository'].update(beta=False, available_version='v1.5.9')
        self.snapshot['update']['attributes']['latest_version'] = 'v1.5.9'
        failures = module.validate_snapshot(self.tag, self.snapshot)
        self.assertTrue(any('generic update' in x for x in failures))
        self.assertTrue(any('Beta releases' in x for x in failures))

    def test_wrong_runtime_and_pending_restart_fail(self):
        self.snapshot.update(manifest_version='1.5.9', entries_loaded=False)
        self.snapshot['repository']['pending_upgrade'] = True
        self.assertGreaterEqual(len(module.validate_snapshot(self.tag, self.snapshot)), 3)

    def test_unknown_or_missing_values_fail_closed(self):
        for field in ['repository', 'update', 'provider', 'manifest_version', 'ha_state', 'entries_loaded']:
            with self.subTest(field=field):
                snapshot = deepcopy(self.snapshot)
                snapshot.pop(field)
                self.assertTrue(module.validate_snapshot(self.tag, snapshot))

    def test_wrong_repository_and_unavailable_entity_fail(self):
        self.snapshot['repository']['id'] = 'different'
        self.snapshot['update']['state'] = 'unavailable'
        self.assertGreaterEqual(len(module.validate_snapshot(self.tag, self.snapshot)), 2)
