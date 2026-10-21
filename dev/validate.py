"""Run isolated acceptance checks locally and in CI without hiding later failures."""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
from importlib import metadata
import json
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


def preflight() -> dict:
    """Fail before tests when the local runtime does not match declared CI inputs."""
    problems = []
    versions = {"python": sys.version.split()[0]}
    if sys.version_info[:2] != PYTHON_MINOR:
        problems.append("Python 3.14 is required, not " + versions["python"])
    for line in REQUIREMENTS.read_text().splitlines():
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
        result.extend((path.stem, [sys.executable, str(path)]) for path in scripts)
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


def markdown(results: list[dict]) -> str:
    lines = ["# Validation Results", "", "| Check | Result | Seconds |",
             "| --- | --- | --- |"]
    lines.extend(f"| {r['name']} | {'PASS' if r['passed'] else 'FAIL'} | {r['seconds']} |"
                 for r in results)
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", action="append", choices=("unit", "security", "ha"))
    parser.add_argument("--list", action="store_true", help="List checks without requiring HA")
    parser.add_argument("--preflight", action="store_true", help="Check versions without running tests")
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
        versions = preflight()
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(versions), flush=True)
    if args.preflight:
        return 0
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output or ROOT / ".local/validation" / stamp
    results = run_checks(items, output, args.timeout)
    (output / "results.json").write_text(json.dumps({"environment": versions, "checks": results}, indent=2))
    (output / "summary.md").write_text(markdown(results))
    print(f"Results: {output}", flush=True)
    return int(any(not result["passed"] for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
