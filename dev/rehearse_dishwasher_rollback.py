"""Rehearse an exact-package dishwasher storage rollback with synthetic HA state."""

import argparse
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch


LEARNING = {
    "schema_version": 1,
    "instances": {
        "1": {
            "runs": 42,
            "program_models": {"Eco50": {"runs": 32}, "Quick45": {"runs": 10}},
            "last_cycle": {"program": "Quick45", "energy_kwh": 0.66},
        },
        "2": {"runs": 19, "program_models": {"Cotton": {"runs": 19}}},
    },
}
SAFE_BASELINE = {
    "active": True,
    "auto_mode_enabled": False,
    "auto_negative_price_enabled": False,
    "door_opened_since_last_cycle": False,
    "request": None,
}


async def phase(action: str, package: Path, directory: Path) -> None:
    sys.path.insert(0, str(package))
    from homeassistant.core import HomeAssistant
    from custom_components.load_optimizer.legacy_runtime import LegacyRuntime
    from custom_components.load_optimizer.orchestration import NativeOrchestrator

    hass = HomeAssistant(str(directory))
    hass.config.skip_pip = True
    entry = SimpleNamespace(entry_id="rollback_fixture", data={}, options={})
    control = NativeOrchestrator(hass, entry, SimpleNamespace(snapshot=None))
    learning = LegacyRuntime(hass)

    async def forbid_service(*args, **kwargs):
        raise AssertionError("This storage-only trial must not call services")

    with patch("homeassistant.core.ServiceRegistry.async_call", new=forbid_service):
        try:
            await control.async_load()
            if action == "seed":
                control.state.update(SAFE_BASELINE)
                control.program_options = ["engine", "Eco50", "Quick45"]
                await control._async_save()
                await learning.async_import_state(deepcopy(LEARNING))
                return
            await learning.async_load()
            assert learning.state == LEARNING, "Learned appliance records changed"
            expected = {**SAFE_BASELINE}
            if action == "restart":
                request = control.state["request"]
                assert request["normal_wash"] is True
                assert request["window_start"] == "2026-11-01T21:00:00+00:00"
                assert request["window_end"] == "2026-11-02T07:00:00+00:00"
                expected["request"] = request
            assert {key: control.state[key] for key in expected} == expected
            assert control.program_options == ["engine", "Eco50", "Quick45"]
            assert control._execution_task is None
            if action == "upgrade":
                control.configure_schedule({"instance_id": "1", "tariff_timezone": "Europe/London"})
                control._new_normal_request(datetime(2026, 11, 1, 23, tzinfo=timezone.utc), automatic=False)
                await control._async_save()
                persisted = await control.store.async_load()
                assert persisted["state"]["request"]["normal_wash"] is True
                assert persisted["state"]["request"]["window_end"]
        finally:
            await hass.async_stop(force=True)


def rehearse(baseline: str, candidate: str) -> None:
    from fingerprint_install import PACKAGE, archive_files, archived_package, fingerprint

    with TemporaryDirectory(prefix="load-optimizer-rollback-") as temp:
        root = Path(temp)
        packages = {}
        commits = set()
        for role, ref in (("baseline", baseline), ("candidate", candidate)):
            commit, archive = archived_package(ref)
            files = list(archive_files(archive))
            identity = fingerprint(files)
            commits.add(commit)
            package = packages[role] = root / role
            for name, content in files:
                path = package / PACKAGE / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            print(role, json.dumps({**identity, "commit": commit}, sort_keys=True), flush=True)
        if len(commits) != 2:
            raise ValueError("The rehearsal needs two different commits")

        def run(action: str, role: str, directory: Path):
            subprocess.run(
                [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--phase",
                 action, str(packages[role]), str(directory)],
                check=True, timeout=120,
            )
            print(f"{action}: synthetic storage verified using {role} package", flush=True)

        old, backup, upgraded, rolled_back = (root / name for name in ("old", "backup", "upgrade", "rollback"))
        old.mkdir()
        run("seed", "baseline", old)
        shutil.copytree(old, backup)
        shutil.copytree(backup, upgraded)
        run("upgrade", "candidate", upgraded)
        run("restart", "candidate", upgraded)
        # Never boot the older controller against a pending request written by
        # the candidate. Rollback restores the matching pre-upgrade store.
        shutil.copytree(backup, rolled_back)
        run("verify", "baseline", rolled_back)
        run("verify", "candidate", rolled_back)
        print("Synthetic rollback passed. No running HA instance or device was contacted.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", nargs=3, metavar=("ACTION", "PACKAGE", "CONFIG"), help=argparse.SUPPRESS)
    parser.add_argument("--baseline", help="Trusted stable Git tag or commit")
    parser.add_argument("--candidate", default="HEAD", help="Trusted candidate Git tag or commit")
    args = parser.parse_args()
    if args.phase:
        action, package, directory = args.phase
        asyncio.run(phase(action, Path(package), Path(directory)))
    elif args.baseline:
        rehearse(args.baseline, args.candidate)
    else:
        parser.error("--baseline is required")


if __name__ == "__main__":
    main()
