"""Check a proposed or already published Load Optimizer prerelease, without writes."""

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
VALIDATION_EVENTS = {"push", "workflow_dispatch"}


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


def check_workflow(run: dict, commit: str) -> None:
    if run.get("headSha") != commit:
        raise ValueError("GitHub validation belongs to a different commit")
    if (run.get("name") != "Validate" or run.get("status") != "completed"
            or run.get("conclusion") != "success"):
        raise ValueError("The Validate workflow must complete successfully")
    if run.get("event") not in VALIDATION_EVENTS:
        raise ValueError("Use validation of the exact commit, not a pull request or scheduled run")
    jobs = run.get("jobs") or []
    names = [
        "Pinned Home Assistant compatibility"
        if job.get("name") == "Current Home Assistant compatibility" else job.get("name")
        for job in jobs
    ]
    if set(names) != REQUIRED_JOBS or len(names) != len(REQUIRED_JOBS) or any(
        job.get("status") != "completed" or job.get("conclusion") != "success" for job in jobs
    ):
        raise ValueError("All six expected validation jobs must pass")


def tag_commit(ref: str, results: str) -> str | None:
    targets = {}
    for line in results.splitlines():
        parts = line.split("\t")
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{40}", parts[0]):
            raise ValueError("Unexpected remote tag response")
        sha, name = parts
        if name not in {ref, ref + "^{}"} or name in targets:
            raise ValueError("Unexpected remote tag response")
        targets[name] = sha
    if targets and ref not in targets:
        raise ValueError("Remote tag object is missing")
    return targets.get(ref + "^{}", targets.get(ref))


def check_publication(release: dict, tag: str, target: str | None, commit: str) -> None:
    if target != commit:
        raise ValueError("The published tag does not point to the validated commit")
    if (release.get("tagName") != tag or release.get("isDraft") is not False
            or release.get("isPrerelease") is not True):
        raise ValueError("Expected a published GitHub prerelease, not a draft or stable release")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("run_id", type=int)
    parser.add_argument("--gh", default="gh", help="Path to the GitHub CLI")
    parser.add_argument("--commit", default="HEAD", help="Local Git ref to the exact candidate")
    parser.add_argument("--published", action="store_true", help="Verify an existing release and its remote tag")
    args = parser.parse_args()
    try:
        if command("git", "status", "--porcelain"):
            raise ValueError("Commit or separate local changes before validating a release")
        git_ref = args.commit + "^{commit}"
        commit = command("git", "rev-parse", "--verify", "--end-of-options", git_ref)
        integration = f"{commit}:custom_components/load_optimizer/"
        check_versions(
            args.tag,
            json.loads(command("git", "show", integration + "manifest.json"))["version"],
            command("git", "show", integration + "legacy/app_runtime.py"),
            command("git", "show", f"{commit}:CHANGELOG.md"),
        )
        ref = f"refs/tags/{args.tag}"
        target = tag_commit(ref, command("git", "ls-remote", "--tags", f"https://github.com/{REPO}.git",
                                        ref, ref + "^{}"))
        if args.published:
            release = json.loads(command(args.gh, "release", "view", args.tag, "-R", REPO,
                                         "--json", "tagName,isDraft,isPrerelease"))
            check_publication(release, args.tag, target, commit)
        elif target or command("git", "tag", "--list", args.tag):
            raise ValueError("The proposed tag already exists")
        run = json.loads(command(args.gh, "run", "view", str(args.run_id), "-R", REPO, "--json",
                                 "name,headSha,status,conclusion,jobs,event"))
        check_workflow(run, commit)
        if (command("git", "rev-parse", "--verify", "--end-of-options", git_ref) != commit
                or command("git", "status", "--porcelain")):
            raise ValueError("The candidate changed during preflight")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Preflight failed: {error}\n")
    state = "verified published prerelease" if args.published else "unused proposed prerelease tag"
    print(f"{args.tag}: {state} for {commit}, matching metadata and six passing jobs.")
    print("No tag or release created. Confirm candidate scope and safe owner upgrade separately.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
