"""Exercise real Home Assistant options, reloads and persisted EV identity.

Run separately from the stub-based unit suite with Home Assistant installed.
An optional config directory permits restart and stable rollback checks in
fresh Python processes. All sources are synthetic and Ofgem I/O is mocked.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import sys
import tempfile
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from homeassistant.bootstrap import async_from_config_dict
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.config_validation import custom_serializer
from homeassistant import loader
from voluptuous_serialize import convert

DOMAIN = "load_optimizer"
TITLE = "Development EV"
SOURCES = {
    "tariff_entity": "sensor.dev_rates",
    "battery_entity": "sensor.dev_battery",
    "battery_capacity_entity": "sensor.dev_capacity",
    "charge_power_kw": 7.2,
    "target_percent": 90,
    "target_percent_entity": "sensor.dev_target",
    "connection_status_entity": "sensor.dev_connection",
    "charger_efficiency": 0.9,
    "slot_minutes": 30,
    "ready_by": "23:59",
    "tariff_timezone": "Europe/London",
    "tariff_price_unit": "p_per_kwh",
    "price_cap_region": "North Western England",
    "price_cap_payment_method": "direct_debit",
}


def seed_sources(hass: HomeAssistant) -> None:
    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    rates = [
        {"start": (start + timedelta(minutes=30 * index)).isoformat(),
         "end": (start + timedelta(minutes=30 * (index + 1))).isoformat(),
         "value_inc_vat": 5 + index % 10}
        for index in range(96)
    ]
    hass.states.async_set("sensor.dev_rates", "ready", {"rates": rates})
    for name, value in (("battery", 40), ("capacity", 60), ("target", 80),
                        ("connection", "connected")):
        hass.states.async_set(f"sensor.dev_{name}", value)


def identities(hass: HomeAssistant, entry_id: str) -> dict[str, str]:
    registry = er.async_get(hass)
    return {
        entry.unique_id: entry.entity_id
        for entry in er.async_entries_for_config_entry(registry, entry_id)
    }


def device_ids(hass: HomeAssistant, entry_id: str) -> list[str]:
    return sorted({entry.device_id for entry in er.async_entries_for_config_entry(
        er.async_get(hass), entry_id
    ) if entry.device_id is not None})


async def prepare_ui_fixture(hass: HomeAssistant) -> None:
    """Create a test-only local account, without onboarding cloud integrations."""
    from homeassistant.auth.const import GROUP_ID_ADMIN
    from homeassistant.components.onboarding import OnboardingStorage
    from homeassistant.components.onboarding.const import STEPS

    if not any(user.name == "Development tester" for user in await hass.auth.async_get_users()):
        provider = hass.auth.get_auth_provider("homeassistant", None)
        await provider.async_initialize()
        user = await hass.auth.async_create_user("Development tester", group_ids=[GROUP_ID_ADMIN])
        await provider.async_add_auth("devtest", "Local-EV-Acceptance-Only")
        credentials = await provider.async_get_or_create_credentials({"username": "devtest"})
        await hass.auth.async_link_user(user, credentials)
    await OnboardingStorage(hass, 4, "onboarding", private=True).async_save({"done": list(STEPS)})
    if onboarding := hass.data.get("onboarding"):
        onboarding.onboarded = True
        for listener in onboarding.listeners:
            listener()


async def edit(hass: HomeAssistant, entry_id: str, section: str, values: dict):
    flow = await hass.config_entries.options.async_init(entry_id)
    assert flow["menu_options"] == ["ev", "price_cap"], flow
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"next_step_id": section}
    )
    assert flow["step_id"] == section, flow
    convert(flow["data_schema"], custom_serializer=custom_serializer)
    result = await hass.config_entries.options.async_configure(flow["flow_id"], values)
    assert result["type"] == "create_entry", result
    await hass.async_block_till_done()


async def run(config_dir: Path, phase: str, serve: bool = False) -> None:
    hass = HomeAssistant(str(config_dir))
    loader.async_setup(hass)
    seed_sources(hass)
    # No live source, AI provider, charger, add-on or appliance is contacted.
    with patch(
        "custom_components.load_optimizer.price_cap.PriceCapManager.async_status",
        new=AsyncMock(return_value={"status": "not_configured", "source": "test"}),
    ):
        try:
            config = {
                "homeassistant": {"name": "Load Optimizer isolated acceptance",
                                  "time_zone": "Europe/London"},
                "http": {"server_host": "127.0.0.1", "server_port": 8128},
            }
            if serve:
                config["frontend"] = {}
            assert await async_from_config_dict(config, hass) is hass
            await hass.async_start()
            await hass.async_block_till_done()
            entries = hass.config_entries.async_entries(DOMAIN)
            if phase == "edit":
                assert not entries, "Use a fresh isolated config directory for the edit phase"
                flow = await hass.config_entries.flow.async_init(
                    DOMAIN, context={"source": "user"}
                )
                flow = await hass.config_entries.flow.async_configure(
                    flow["flow_id"], {"name": TITLE, "load_type": "ev_charging"}
                )
                convert(flow["data_schema"], custom_serializer=custom_serializer)
                result = await hass.config_entries.flow.async_configure(
                    flow["flow_id"], dict(SOURCES)
                )
                assert result["type"] == "create_entry", result
                await hass.async_block_till_done()
                entries = hass.config_entries.async_entries(DOMAIN)
            assert len(entries) == 1
            entry = entries[0]
            assert entry.state.value == "loaded", entry.state
            original_data = dict(entry.data)
            before_ids = identities(hass, entry.entry_id)
            before_devices = device_ids(hass, entry.entry_id)
            assert len(before_ids) == 9, before_ids
            assert len(before_devices) == 1, before_devices
            assert not any(key.startswith(("switch.", "button."))
                           for key in before_ids.values()), "EV must remain advisory"

            if phase == "edit":
                for entity_id in before_ids.values():
                    assert "None" not in hass.states.get(entity_id).name
                coordinator = hass.data[DOMAIN][entry.entry_id]
                assert coordinator.data["plan"]["target_percent"] == 80
                values = {key: value for key, value in SOURCES.items()
                          if key not in {"target_percent_entity", "connection_status_entity",
                                         "ready_by", "price_cap_region",
                                         "price_cap_payment_method"}}
                values.update({"target_percent": 85, "charge_power_kw": 3.6})
                invalid = await hass.config_entries.options.async_init(entry.entry_id)
                invalid = await hass.config_entries.options.async_configure(
                    invalid["flow_id"], {"next_step_id": "ev"}
                )
                invalid = await hass.config_entries.options.async_configure(
                    invalid["flow_id"], {**values, "ready_by": "25:00"}
                )
                assert invalid["type"] == "form"
                assert invalid["errors"] == {"ready_by": "invalid_ready_by"}
                assert hass.data[DOMAIN][entry.entry_id] is coordinator
                assert not entry.options
                convert(invalid["data_schema"], custom_serializer=custom_serializer)
                hass.config_entries.options.async_abort(invalid["flow_id"])
                await edit(hass, entry.entry_id, "ev", values)
                assert hass.data[DOMAIN][entry.entry_id] is not coordinator
                assert dict(entry.data) == original_data
                assert identities(hass, entry.entry_id) == before_ids
                for key in ("target_percent_entity", "connection_status_entity", "ready_by"):
                    assert entry.options[key] == ""
                plan = hass.data[DOMAIN][entry.entry_id].data["plan"]
                assert plan["status"] == "ready", plan
                assert plan["target_percent"] == 85, plan
                assert plan["deadline"] is None, plan
                assert plan["slot_energy_kwh"] == 1.8, plan
                await edit(hass, entry.entry_id, "price_cap", {
                    "price_cap_region": "Merseyside and Northern Wales",
                    "price_cap_payment_method": "prepayment",
                })
                assert entry.options["target_percent"] == 85
                assert entry.options["charge_power_kw"] == 3.6
                assert entry.options["ready_by"] == ""
                assert dict(entry.data) == original_data
                assert await hass.config_entries.async_reload(entry.entry_id)
                await hass.async_block_till_done()
                snapshot = {"entry_id": entry.entry_id, "identities": before_ids,
                            "device_ids": before_devices, "data": original_data,
                            "options": dict(entry.options)}
                (config_dir / "acceptance.json").write_text(json.dumps(snapshot, indent=2))
            else:
                snapshot = json.loads((config_dir / "acceptance.json").read_text())
                assert entry.entry_id == snapshot["entry_id"]
                assert before_ids == snapshot["identities"]
                assert before_devices == snapshot["device_ids"]
                assert dict(entry.data) == snapshot["data"]
                assert dict(entry.options) == snapshot["options"]
                plan = hass.data[DOMAIN][entry.entry_id].data["plan"]
                assert plan["status"] == "ready", plan
                assert plan["target_percent"] == 85
                assert plan["deadline"] is None
                assert plan["slot_energy_kwh"] == 1.8
            assert identities(hass, entry.entry_id) == before_ids
            assert device_ids(hass, entry.entry_id) == before_devices
            print(f"EV {phase}: real HA flow/reload, advisory plan and stable identity passed")
            if serve:
                await prepare_ui_fixture(hass)
                print("Isolated development UI: http://127.0.0.1:8128", flush=True)
                await asyncio.Event().wait()
        finally:
            await hass.async_stop(force=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path)
    parser.add_argument("--phase", choices=("edit", "verify"), default="edit")
    parser.add_argument("--serve", action="store_true", help="Keep the isolated UI open for inspection")
    args = parser.parse_args()
    if args.config_dir:
        if args.config_dir.exists() and any(args.config_dir.iterdir()):
            snapshot_path = args.config_dir / "acceptance.json"
            if args.phase != "verify" or not snapshot_path.is_file():
                parser.error("Only use a fresh directory or this test's acceptance fixture")
            snapshot = json.loads(snapshot_path.read_text())
            if snapshot.get("data", {}).get("tariff_entity") != SOURCES["tariff_entity"]:
                parser.error("Refusing to load configuration that is not the synthetic EV fixture")
        args.config_dir.mkdir(parents=True, exist_ok=True)
        components = args.config_dir / "custom_components"
        if not components.exists():
            components.symlink_to(ROOT / "custom_components", target_is_directory=True)
        asyncio.run(run(args.config_dir, args.phase, args.serve))
    else:
        with tempfile.TemporaryDirectory(prefix="load-optimizer-ev-") as directory:
            path = Path(directory)
            (path / "custom_components").symlink_to(
                ROOT / "custom_components", target_is_directory=True
            )
            asyncio.run(run(path, "edit"))
            asyncio.run(run(path, "verify"))
