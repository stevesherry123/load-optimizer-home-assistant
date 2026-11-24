from copy import deepcopy
import unittest

from dev.check_beta_release import REQUIRED_JOBS, check_versions, check_workflow, check_release_progression, release_order


class BetaReleasePreflightTests(unittest.TestCase):
    def test_requires_beta_version_parity_and_changelog(self):
        valid = ("v1.7.0-beta.12", "1.7.0-beta.12",
                 'APP_VERSION = "1.7.0-beta.12"', "## 1.7.0-beta.12")
        check_versions(*valid)
        for index, invalid in enumerate(("v1.7.0", "1.7.0-beta.11",
                                          'APP_VERSION = "1.7.0-beta.11"', "## Unreleased")):
            values = list(valid)
            values[index] = invalid
            with self.subTest(index=index), self.assertRaises(ValueError):
                check_versions(*values)

    def test_historical_alpha_and_release_candidate_versions_are_ordered(self):
        ordered = ['v1.4.0-alpha.1', 'v1.4.0-beta.1', 'v1.4.0-rc.1', 'v1.4.0']
        self.assertEqual(sorted(ordered, key=release_order), ordered)
        check_release_progression('v1.7.0-beta.12', [{'tagName': 'v1.4.0-alpha.1'}])

    def test_candidate_advances_all_published_release_trains(self):
        releases = [{'tagName': 'v1.7.0-beta.11', 'isDraft': False},
                    {'tagName': 'v1.5.10-beta.1', 'isDraft': False},
                    {'tagName': 'v1.5.9', 'isDraft': False}]
        check_release_progression('v1.7.0-beta.12', releases)
        for candidate in ['v1.5.10-beta.2', 'v1.7.0-beta.11']:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                check_release_progression(candidate, releases)
        with self.assertRaises(ValueError):
            check_release_progression('v1.7.0-beta.12', releases + [{'tagName': 'v1.7.0'}])
        check_release_progression('v1.7.0-beta.12', releases + [{'tagName': 'v2.0.0', 'isDraft': True}])

    def test_rejects_wrong_commit_or_incomplete_validation(self):
        run = {"name": "Validate", "headSha": "candidate", "status": "completed",
               "conclusion": "success", "jobs": [
                   {"name": name, "status": "completed", "conclusion": "success"}
                   for name in sorted(REQUIRED_JOBS)
               ]}
        check_workflow(run, "candidate")
        with self.assertRaisesRegex(ValueError, "different commit"):
            check_workflow(run, "other")
        for conclusion in ("failure", "cancelled", "skipped", None):
            bad = deepcopy(run)
            bad["jobs"][0]["conclusion"] = conclusion
            with self.subTest(conclusion=conclusion), self.assertRaises(ValueError):
                check_workflow(bad, "candidate")
        with self.assertRaises(ValueError):
            check_workflow({**run, "jobs": run["jobs"][:-1]}, "candidate")
