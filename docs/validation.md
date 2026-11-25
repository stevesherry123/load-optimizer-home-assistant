# Reproducible Validation

Use this before pushing runtime changes. The shared beta and local acceptance
runner use Python **3.14**, Home Assistant **2026.10.2** and frontend
**20260930.4**, declared in `dev/requirements-validation.txt`. A preflight rejects
wrong or missing versions rather than treating old-HA success as current-HA evidence.
Python patch versions and platform-specific transitive dependencies may differ;
the report records the actual Python and pinned package versions. This is not a
fully locked cross-platform environment.
Preflight also compares frontend and authentication requirements with the installed
HA source. Simulated HA instances disable package installation; they cannot
silently replace dependencies or download extra components during a test.

## Local Workflow

```sh
python3.14 -m venv .venv-validation
.venv-validation/bin/python -m pip install -r dev/requirements-validation.txt
.venv-validation/bin/python dev/validate.py --preflight
.venv-validation/bin/python dev/validate.py
```

Run from a development checkout, not Home Assistant's live configuration directory.
The acceptance scripts use synthetic entities, temporary configuration and mocked
supplier/AI calls. They do not need HA credentials or household device mappings.
Some tests bind loopback-only ports, so a sandbox may require local-listener approval.
The tests need no connection to the owner's Home Assistant instance.

The runner executes unit, Bandit and every `tests/ha_*_smoke.py` acceptance check
in separate processes. Independent checks keep running after a failure; any
failure or timeout makes the final exit status nonzero. No check is ignored.
Each check has a five-minute timeout, configurable with `--timeout`.
Bandit must report scanned source and no skipped files, in addition to
returning success with no findings.

Reports record the Git commit/branch, dirty working-tree flag, selected suites and
a SHA-256 fingerprint of tracked and unignored source files, including symlinks
and file modes. The runner compares identity before and after checks; a mismatch
returns failure even if individual checks passed. The report directory itself
and ignored files are excluded from that fingerprint. No source contents or
credential values are included in the identity record.

Dirty working-tree runs remain useful for development, but their commit alone
does not identify the changed code. Commit the candidate and rerun from a clean
tree for release evidence. If Git/source identity cannot be verified, checks can
still execute but the report explicitly lacks verified revision evidence; do not
use that report as a release gate. See [release readiness](release-readiness.md).

Results go to a unique ignored `.local/validation/` directory with per-check logs,
`results.json` and `summary.md`. `--suite ha` runs just HA checks; `--list` lists
checks without importing HA. Do not commit generated logs or private local files.
Gitleaks, HACS and hassfest remain additional GitHub checks, not replaced by this runner.

The optional real-card browser harness is a separate explicit `--suite browser`.
It needs Playwright, Chrome and the official ApexCharts Card asset configured as
described in that script. It is not part of the standard HA dependency set.
Requesting that suite without its prerequisites fails; it is never reported as
a pass merely because it was not selected. Standard HA checks still execute the
shipped chart JavaScript across browser timezones and profile preferences.

## Pinned compatibility environment

The second GitHub HA job tests **2026.11.0**, using
`dev/requirements-validation-compatibility.txt`. This is a pinned compatibility
check, not a claim to track the latest release automatically. It runs every
standard HA acceptance check, including EV control and source-consistency cases,
with the same environment preflight, source identity and failure reporting.
Use `--requirements dev/requirements-validation-compatibility.txt --suite ha`
with the runner in a separate environment installed from that requirements file.
The default minimum-version environment and its pins remain separate.

## GitHub Triggers

- Pull requests run the full validation workflow, including the prospective merge.
- Pushes to `main` validate the merged integration.
- Beta pushes with an open pull request use its PR run, not a duplicate push run.
- A development branch without a PR requires manual `Validate` dispatch before
  promotion. Do not interpret the absence of a push run as a pass.
- The scheduled stable check and manual dispatch remain enabled.

Failed acceptance logs and the full pass/fail table are published in the same run.
Dependency installation/preflight failures remain blocking and are reported as
setup failures, not successful acceptance. Security, HACS and hassfest failures
remain blocking. GitHub failure notifications are not muted.

## Change And Publication Boundary

Changing the HA/provider minimum requires updating the complete fixture suite
and running it in the matching environment before push. Run all checks before
attempting one GitHub validation, rather than fixing one remote failure at a time.
Preserve the failing report when diagnosing a regression.

These changes do not bump a release version, publish to HACS, approve a catalogue
submission or install/restart Home Assistant. Those remain separate decisions.
