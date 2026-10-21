"""Prove trial values restore through a real HA stop/start, without hardware."""

import asyncio
import argparse
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import yaml
from homeassistant import loader
from homeassistant.bootstrap import async_from_config_dict
from homeassistant.core import HomeAssistant


async def run_phase(directory, restart):
    root = Path(__file__).resolve().parents[1]
    package = yaml.safe_load((root / "dev/ev-test-package.yaml").read_text())
    config = {key: package[key] for key in ("input_number", "input_boolean")}
    hass = HomeAssistant(directory)
    hass.config.skip_pip = True
    loader.async_setup(hass)
    try:
        assert await async_from_config_dict(deepcopy(config), hass) is hass
        await hass.async_start()
        await hass.async_block_till_done()
        if not restart:
            for suffix, value in (("battery_percent", 61), ("capacity_kwh", 0.6), ("target_percent", 99)):
                await hass.services.async_call("input_number", "set_value", {
                    "entity_id": "input_number.ev_trial_" + suffix, "value": value}, blocking=True)
            await hass.services.async_call("input_boolean", "turn_on", {
                "entity_id": "input_boolean.ev_trial_connected"}, blocking=True)
        else:
            for suffix, value in (("battery_percent", 61), ("capacity_kwh", 0.6), ("target_percent", 99)):
                assert float(hass.states.get("input_number.ev_trial_" + suffix).state) == value
            assert hass.states.get("input_boolean.ev_trial_connected").state == "on"
    finally:
        await hass.async_stop(force=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory")
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    if args.directory:
        asyncio.run(run_phase(args.directory, args.restore))
    else:
        with TemporaryDirectory() as directory:
            command = [sys.executable, str(Path(__file__).resolve()), "--directory", directory]
            subprocess.run(command, check=True, timeout=60)
            subprocess.run([*command, "--restore"], check=True, timeout=60)
        print("Trial restart: battery, capacity, target and connection restored across fresh HA processes")
