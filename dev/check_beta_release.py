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
