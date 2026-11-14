"""Fail closed on incomplete or unsuccessful Bandit scans."""

import json
import subprocess
import sys


def scan_passed(returncode: int, report: object) -> bool:
    if returncode or not isinstance(report, dict):
        return False
    metrics = report.get("metrics")
    totals = metrics.get("_totals") if isinstance(metrics, dict) else None
    lines = totals.get("loc") if isinstance(totals, dict) else None
    return (
        report.get("errors") == []
        and report.get("results") == []
        and type(lines) is int
        and lines > 0
    )


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "bandit", "-r", "custom_components/load_optimizer", "-f", "json"],
        capture_output=True, text=True, check=False,
    )
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    try:
        report = json.loads(result.stdout)
    except ValueError:
        print("Bandit did not return a valid report.", file=sys.stderr)
        return 1
    if not scan_passed(result.returncode, report):
        print("Bandit scan failed or was incomplete.", file=sys.stderr)
        if isinstance(report, dict):
            for skipped in report.get("errors") or []:
                print(f"Skipped: {skipped.get('filename', 'unknown file')}", file=sys.stderr)
            for finding in report.get("results") or []:
                print(f"{finding.get('test_id')}: {finding.get('filename')}:{finding.get('line_number')}",
                      file=sys.stderr)
        return 1
    print(f"Bandit scanned {report['metrics']['_totals']['loc']} lines without findings or skipped files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
