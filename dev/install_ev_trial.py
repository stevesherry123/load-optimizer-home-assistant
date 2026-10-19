"""Explicit owner-only file installation; never restart HA or operate a load."""

import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from urllib.request import urlopen
from zipfile import ZipFile


def install(root, commit, switch, power, energy):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Use an exact reviewed commit, not a moving branch")
    for entity_id, domain in ((switch, "switch"), (power, "sensor"), (energy, "sensor")):
        if not re.fullmatch(domain + r"\.[a-z0-9_]+", entity_id):
            raise ValueError("Invalid trial source ID")
    root = root.resolve(strict=True)
    config = (root / "configuration.yaml").read_text()
    if "packages: !include_dir_named packages" not in config:
        raise ValueError("This helper requires the existing packages directory include")
    target = root / "custom_components/load_optimizer"
    package = root / "packages/lo_ev_charging_trial.yaml"
    if package.exists():
        raise ValueError("Trial package already exists; review it rather than overwrite it")
    if not (target / "manifest.json").is_file():
        raise ValueError("Existing integration was not found")
    url = "https://codeload.github.com/stevesherry123/load-optimizer-home-assistant/zip/" + commit
    with urlopen(url, timeout=45) as response:  # nosec B310: fixed HTTPS host + validated SHA
        content = response.read(32 * 1024 * 1024 + 1)
    if len(content) > 32 * 1024 * 1024:
        raise ValueError("Unexpected archive size")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rollback = root / ".lo-ev-trial-rollback" / stamp
    with tempfile.TemporaryDirectory(prefix="lo-ev-stage-", dir=target.parent) as staging:
        staged = Path(staging) / "load_optimizer"
        staged.mkdir()
        with ZipFile(io.BytesIO(content)) as archive:
            prefix = "load-optimizer-home-assistant-" + commit + "/"
            component = prefix + "custom_components/load_optimizer/"
            for item in archive.infolist():
                if not item.filename.startswith(component) or item.is_dir():
                    continue
                relative = PurePosixPath(item.filename[len(component):])
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("Invalid archive member")
                data = archive.read(item)
                if relative.suffix == ".py":
                    compile(data, str(relative), "exec")
                destination = staged.joinpath(*relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            trial = archive.read(prefix + "dev/ev-test-package.yaml").decode()
        trial = trial.replace("switch.ev_trial_load", switch).replace("sensor.ev_trial_load_power", power)
        json.loads((staged / "manifest.json").read_text())
        (staged / "_owner_trial_build.json").write_text(json.dumps({"commit": commit, "installed_at": stamp,
            "branch": "feature/ev-charger-control", "released": False}))
        rollback.mkdir(parents=True)
        # Only integration source is retained, not HA learning/history/config stores.
        target.rename(rollback / "load_optimizer")
        try:
            staged.rename(target)
            package.parent.mkdir(parents=True, exist_ok=True)
            package.write_text(trial)
        except Exception:
            if target.exists():
                shutil.rmtree(target)
            (rollback / "load_optimizer").rename(target)
            if package.exists():
                package.unlink()
            raise
    print(json.dumps({"installed_commit": commit, "rollback_directory": str(rollback),
                      "package": str(package), "restarted": False, "physical_commands": 0,
                      "power_source": power, "energy_source": energy}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--switch", required=True)
    parser.add_argument("--power", required=True)
    parser.add_argument("--energy", required=True)
    args = parser.parse_args()
    install(args.config_dir, args.commit, args.switch, args.power, args.energy)
