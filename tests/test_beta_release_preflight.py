from copy import deepcopy
import unittest

from dev.check_beta_release import (
    REQUIRED_JOBS, check_release_progression, release_order,
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

    def test_stable_version_requires_explicit_channel_and_matching_metadata(self):
        valid = ("v1.7.0", "1.7.0", 'APP_VERSION = "1.7.0"', "## 1.7.0")
        check_versions(*valid, stable=True)
        with self.assertRaises(ValueError):
            check_versions(*valid)
        with self.assertRaises(ValueError):
            check_versions("v1.7.0-beta.13", "1.7.0-beta.13",
                           'APP_VERSION = "1.7.0-beta.13"', "## 1.7.0-beta.13", stable=True)
        with self.assertRaises(ValueError):
            check_versions("v1.7.0", "1.7.0-beta.13", valid[2], valid[3], stable=True)
        check_release_progression("v1.7.0", [{"tagName": "v1.7.0-beta.12"}])

    def test_stable_audit_rejects_draft_prerelease_or_wrong_tag_commit(self):
        release = {"tagName": "v1.7.0", "isDraft": False, "isPrerelease": False}
        check_publication(release, "v1.7.0", "candidate", "candidate", stable=True)
        for key, value in (("isDraft", True), ("isPrerelease", True), ("tagName", "other")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                check_publication({**release, key: value}, "v1.7.0", "candidate", "candidate", stable=True)
        with self.assertRaises(ValueError):
            check_publication(release, "v1.7.0", "other", "candidate", stable=True)

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
