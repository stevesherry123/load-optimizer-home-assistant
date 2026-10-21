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

Results go to a unique ignored `.local/validation/` directory with per-check logs,
`results.json` and `summary.md`. `--suite ha` runs just HA checks; `--list` lists
checks without importing HA. Do not commit generated logs or private local files.
Gitleaks, HACS and hassfest remain additional GitHub checks, not replaced by this runner.

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
