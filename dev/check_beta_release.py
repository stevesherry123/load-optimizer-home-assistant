"""Read-only release preflight for a new Load Optimizer GitHub prerelease."""

import argparse
import ast
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPO = "stevesherry123/load-optimizer-home-assistant"
REQUIRED_JOBS = {
    "Security and credential scan", "Python tests", "Minimum Home Assistant imports",
    "Pinned Home Assistant compatibility", "HACS validation", "Home Assistant hassfest",
}


def command(*args: str) -> str:
    return subprocess.run(args, cwd=ROOT, check=True, capture_output=True,
                          text=True, timeout=30).stdout.strip()


def check_versions(tag: str, manifest: str, runtime_source: str, changelog: str) -> None:
    if not re.fullmatch(r"v\d+\.\d+\.\d+-beta\.[1-9]\d*", tag):
        raise ValueError("Only new vX.Y.Z-beta.N tags are supported")
    versions = [
        ast.literal_eval(node.value)
        for node in ast.parse(runtime_source).body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "APP_VERSION" for target in node.targets)
    ]
    if tag != f"v{manifest}" or versions != [manifest]:
        raise ValueError("Tag, manifest and runtime versions do not match")
    if f"## {manifest}" not in changelog.splitlines():
        raise ValueError("The candidate needs a matching changelog heading")


def release_order(tag: str) -> tuple[int, ...]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc)\.([1-9]\d*))?", tag)
    if match is None:
        raise ValueError("Cannot compare published release version: " + tag)
    major, minor, patch, stage, number = match.groups()
    rank = {"alpha": 0, "beta": 1, "rc": 2, None: 3}
    return (int(major), int(minor), int(patch), rank[stage], int(number or 0))


def check_release_progression(tag: str, releases: list[dict]) -> None:
    """One public beta stream must not advertise older builds after newer ones."""
    candidate = release_order(tag)
    for release in releases:
        if release.get("isDraft"):
            continue
        published = release["tagName"]
        if release_order(published) >= candidate:
            raise ValueError("Candidate must advance the public release stream beyond " + published)


def check_workflow(run: dict, commit: str) -> None:
    if run.get("headSha") != commit:
        raise ValueError("GitHub validation belongs to a different commit")
    if (run.get("name") != "Validate" or run.get("status") != "completed"
            or run.get("conclusion") != "success"):
        raise ValueError("The Validate workflow must complete successfully")
    jobs = run.get("jobs") or []
    names = [job.get("name") for job in jobs]
    if set(names) != REQUIRED_JOBS or len(names) != len(REQUIRED_JOBS) or any(
        job.get("status") != "completed" or job.get("conclusion") != "success" for job in jobs
    ):
        raise ValueError("All six expected validation jobs must pass")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("run_id", type=int)
    parser.add_argument("--gh", default="gh", help="Path to the GitHub CLI")
    args = parser.parse_args()
    try:
        if command("git", "status", "--porcelain"):
            raise ValueError("Commit or separate local changes before validating a release")
        commit = command("git", "rev-parse", "HEAD")
        integration = "HEAD:custom_components/load_optimizer/"
        check_versions(
            args.tag,
            json.loads(command("git", "show", integration + "manifest.json"))["version"],
            command("git", "show", integration + "legacy/app_runtime.py"),
            command("git", "show", "HEAD:CHANGELOG.md"),
        )
        ref = f"refs/tags/{args.tag}"
        if command("git", "tag", "--list", args.tag) or command(
            "git", "ls-remote", "--refs", "--tags", f"https://github.com/{REPO}.git", ref
        ):
            raise ValueError("The proposed tag already exists")
        releases = json.loads(command(args.gh, "release", "list", "-R", REPO, "--limit", "1000",
                                      "--json", "tagName,isDraft,isPrerelease"))
        if len(releases) >= 1000:
            raise ValueError("Release inventory may be truncated; paginate it before publication")
        check_release_progression(args.tag, releases)
        run = json.loads(command(args.gh, "run", "view", str(args.run_id), "-R", REPO, "--json",
                                 "name,headSha,status,conclusion,jobs"))
        check_workflow(run, commit)
        if command("git", "rev-parse", "HEAD") != commit or command("git", "status", "--porcelain"):
            raise ValueError("The candidate changed during preflight")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Preflight failed: {error}\n")
    print(f"{args.tag}: clean candidate {commit}, matching metadata and six passing jobs.")
    print("No tag or release created. Confirm candidate scope and safe owner upgrade separately.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
