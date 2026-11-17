from copy import deepcopy
import unittest

from dev.check_beta_release import (
    REQUIRED_JOBS,
    check_publication,
    check_versions,
    check_workflow,
    tag_commit,
)


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
        run = {"name": "Validate", "headSha": "candidate", "status": "completed", "event": "push",
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
        for event in ("pull_request", "schedule", None):
            with self.subTest(event=event), self.assertRaisesRegex(ValueError, "exact commit"):
                check_workflow({**run, "event": event}, "candidate")

        job = next(item for item in run["jobs"] if item["name"] == "Pinned Home Assistant compatibility")
        job["name"] = "Current Home Assistant compatibility"
        check_workflow(run, "candidate")
        run["jobs"].append({**job, "name": "Pinned Home Assistant compatibility"})
        with self.assertRaisesRegex(ValueError, "All six"):
            check_workflow(run, "candidate")

    def test_resolves_lightweight_and_annotated_remote_tags(self):
        ref = "refs/tags/v1.5.10-beta.1"
        sha, obj = "a" * 40, "b" * 40
        self.assertIsNone(tag_commit(ref, ""))
        self.assertEqual(tag_commit(ref, f"{sha}\t{ref}"), sha)
        self.assertEqual(tag_commit(ref, f"{obj}\t{ref}\n{sha}\t{ref}^{{}}"), sha)
        for response in (f"{sha}\t{ref}^{{}}", f"{sha}\trefs/heads/main", f"unknown\t{ref}"):
            with self.subTest(response=response), self.assertRaises(ValueError):
                tag_commit(ref, response)

    def test_audit_requires_published_prerelease_and_actual_remote_commit(self):
        tag = "v1.5.10-beta.1"
        release = {"tagName": tag, "isDraft": False, "isPrerelease": True}
        check_publication(release, tag, "candidate", "candidate")
        with self.assertRaisesRegex(ValueError, "validated commit"):
            check_publication(release, tag, "different", "candidate")
        for key, value in (("isDraft", True), ("isPrerelease", False), ("tagName", "other")):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "published GitHub prerelease"):
                check_publication({**release, key: value}, tag, "candidate", "candidate")
