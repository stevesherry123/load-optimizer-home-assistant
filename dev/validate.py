"""Run isolated acceptance checks locally and in CI without hiding later failures."""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
from importlib import metadata
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PYTHON_MINOR = (3, 14)
REQUIREMENTS = ROOT / "dev/requirements-validation.txt"


def ha_runtime_requirements() -> list[str]:
    """Check bootstrap dependencies against HA's own source without importing it."""
    distribution = metadata.distribution("homeassistant")
    frontend = distribution.locate_file("homeassistant/components/frontend/manifest.json")
    totp = distribution.locate_file("homeassistant/auth/mfa_modules/totp.py")
    requirements = json.loads(frontend.read_text())["requirements"]
    tree = ast.parse(totp.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "REQUIREMENTS"
                                               for t in node.targets):
            return requirements + ast.literal_eval(node.value)
    raise ValueError("Could not verify HA authentication dependency requirements")


def preflight(requirements: Path = REQUIREMENTS) -> dict:
    """Fail before tests when the local runtime does not match declared CI inputs."""
    problems = []
    versions = {"python": sys.version.split()[0]}
    if sys.version_info[:2] != PYTHON_MINOR:
        problems.append("Python 3.14 is required, not " + versions["python"])
    for line in requirements.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        package, expected = line.split("==")
        try:
            actual = metadata.version(package)
        except metadata.PackageNotFoundError:
            actual = "missing"
        versions[package] = actual
        if actual != expected:
            problems.append(f"{package}: expected {expected}, found {actual}")
    if versions.get("homeassistant") != "missing":
        try:
            for requirement in ha_runtime_requirements():
                package, expected = requirement.split("==")
                if versions.get(package) != expected:
                    problems.append(f"HA bootstrap requires {requirement}; update validation pins")
        except (OSError, ValueError, metadata.PackageNotFoundError) as error:
            problems.append(f"Could not verify HA bootstrap dependencies: {error}")
    if problems:
        raise ValueError("Validation environment mismatch:\n" + "\n".join(problems))
    return versions


def checks(suites: list[str]) -> list[tuple[str, list[str]]]:
    result = []
    if "unit" in suites:
        result.append(("unit", [sys.executable, "-m", "unittest", "discover", "-s", "tests"]))
    if "security" in suites:
        result.append(("bandit", [sys.executable, "-m", "bandit", "-r", "custom_components/load_optimizer"]))
    if "ha" in suites:
        scripts = sorted((ROOT / "tests").glob("ha_*_smoke.py"),
                         key=lambda p: (p.name != "ha_import_smoke.py", p.name))
        if not any(path.name == "ha_import_smoke.py" for path in scripts):
            raise ValueError("HA acceptance scripts are missing")
        result.extend((path.stem, [sys.executable, str(path)]) for path in scripts
                      if path.name != "ha_chart_browser_smoke.py")
    if "browser" in suites:
        path = ROOT / "tests/ha_chart_browser_smoke.py"
        result.append((path.stem, [sys.executable, str(path)]))
    return result


def run_checks(items, output: Path, timeout: int) -> list[dict]:
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for name, command in items:
        started = time.monotonic()
        log = output / (name + ".log")
        print(f"Starting {name}", flush=True)
        with log.open("w") as stream:
            try:
                process = subprocess.run(command, cwd=ROOT, stdout=stream,
                                         stderr=subprocess.STDOUT, timeout=timeout, check=False)
                code = process.returncode
            except subprocess.TimeoutExpired:
                stream.write(f"\nCheck exceeded {timeout} seconds.\n")
                code = 124
            except OSError as error:
                stream.write(f"\nCould not start check: {error}\n")
                code = 125
        results.append({"name": name, "returncode": code, "passed": code == 0,
                        "seconds": round(time.monotonic() - started, 2), "log": log.name})
        print(f"{'PASS' if code == 0 else 'FAIL'} {name}", flush=True)
    return results


def source_identity(*, root: Path | None = None, exclude: Path | None = None) -> dict:
    """Identify checked-out source without recording file contents or credentials."""
    root = (root or ROOT).resolve()
    def git(*args):
        return subprocess.run(["git", *args], cwd=root, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, check=True, timeout=10).stdout
    try:
        commit = git("rev-parse", "HEAD").decode().strip()
        branch = git("rev-parse", "--abbrev-ref", "HEAD").decode().strip()
        names = git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split(b"\0")
        output = exclude.resolve() if exclude else None
        digest = hashlib.sha256()
        for name in sorted(set(names) - {b""}):
            path = root / os.fsdecode(name)
            if output and path.absolute().is_relative_to(output):
                continue
            if path.is_symlink():
                content = b"symlink\0" + os.fsencode(os.readlink(path))
            elif path.is_file():
                content = b"file\0" + path.read_bytes()
            elif not path.exists():
                content = b"missing\0"
            else:
                raise ValueError("Unsupported source entry")
            mode = str(path.lstat().st_mode & 0o777).encode() if path.exists() or path.is_symlink() else b"missing"
            digest.update(name + b"\0" + mode + b"\0" + hashlib.sha256(content).digest())
        status_args = ["status", "--porcelain", "--untracked-files=all"]
        if output and output.is_relative_to(root.resolve()):
            status_args += ["--", ".", ":(exclude,literal)" + output.relative_to(root.resolve()).as_posix()]
        dirty = bool(git(*status_args))
        return {"available": True, "commit": commit, "branch": branch,
                "worktree_dirty": dirty, "fingerprint_sha256": digest.hexdigest()}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"available": False, "reason": "Source revision could not be verified"}


def markdown(results: list[dict], source: dict | None = None) -> str:
    lines = ["# Validation Results", ""]
    if source:
        before = source["before"]
        if before.get("available"):
            lines.extend([f"Source commit: `{before['commit']}`.",
                          f"Working tree: {'modified' if before['worktree_dirty'] else 'clean'}.",
                          f"Source fingerprint: `{before['fingerprint_sha256']}`."])
        else:
            lines.append("Source identity unavailable; this is not exact-commit release evidence.")
        match = ('yes' if source['unchanged'] else 'NO — rerun validation') if before.get("available") and source["after"].get("available") else 'unverified'
        lines.extend([f"Source identity matched before and after checks: {match}.", ""])
    lines.extend(["| Check | Result | Seconds |", "| --- | --- | --- |"])
    lines.extend(f"| {r['name']} | {'PASS' if r['passed'] else 'FAIL'} | {r['seconds']} |"
                 for r in results)
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", action="append", choices=("unit", "security", "ha", "browser"))
    parser.add_argument("--list", action="store_true", help="List checks without requiring HA")
    parser.add_argument("--preflight", action="store_true", help="Check versions without running tests")
    parser.add_argument("--requirements", type=Path, default=REQUIREMENTS,
                        help="Pinned environment requirements to verify before checks")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    items = checks(args.suite or ["unit", "security", "ha"])
    if args.list:
        print("\n".join(name for name, _ in items))
        return 0
    try:
        versions = preflight(args.requirements)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(versions), flush=True)
    if args.preflight:
        return 0
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output or ROOT / ".local/validation" / stamp
    before = source_identity(exclude=output)
    results = run_checks(items, output, args.timeout)
    after = source_identity(exclude=output)
    source = {"before": before, "after": after, "unchanged": before == after}
    (output / "results.json").write_text(json.dumps({"environment": versions, "checks": results,
                                                   "suites": args.suite or ["unit", "security", "ha"],
                                                   "source": source}, indent=2))
    (output / "summary.md").write_text(markdown(results, source))
    print(f"Results: {output}", flush=True)
    return int(any(not result["passed"] for result in results) or not source["unchanged"])


if __name__ == "__main__":
    raise SystemExit(main())
