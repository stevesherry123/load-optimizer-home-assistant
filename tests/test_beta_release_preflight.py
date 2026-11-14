from copy import deepcopy
import unittest

from dev.check_beta_release import REQUIRED_JOBS, check_versions, check_workflow


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
