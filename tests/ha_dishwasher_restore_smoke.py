"""Restore real scheduling storage into fresh HA instances without device I/O."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homeassistant.core import HomeAssistant
from custom_components.load_optimizer.orchestration import NativeOrchestrator


async def main():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        instances = []
        entry = SimpleNamespace(entry_id="restore_fixture", data={}, options={})
        now = datetime(2026, 11, 6, 22, tzinfo=timezone.utc)

        def fresh(name, source=None):
            path = root / name
            path.mkdir()
            if source is not None:
                shutil.copytree(source / ".storage", path / ".storage")
            hass = HomeAssistant(str(path))
            hass.config.skip_pip = True
            instances.append(hass)
            return path, NativeOrchestrator(hass, entry, None)

        async def forbid_command(registry, domain, service, data, **kwargs):
            assert domain == "persistent_notification", "Storage recovery must not issue device commands"

        with patch("homeassistant.core.ServiceRegistry.async_call", new=forbid_command):
            try:
                original_path, original = fresh("original")
                original.configure_schedule({"instance_id": "1", "tariff_timezone": "Europe/London"})
                original.state.update(active=True, auto_mode_enabled=False,
                                      auto_negative_price_enabled=False)
                original._new_normal_request(now, automatic=False)
                original.state["overnight_start"] = "22:00"
                original.program_options = ["engine", "Eco50"]
                await original._async_save()
                request = deepcopy(original.state["request"])
                assert list((original_path / ".storage").iterdir())

                restored_path, restored = fresh("restored", original_path)
                await restored.async_load()
                assert restored.state["request"] == request
                assert restored.state["execution_status"] == "awaiting_plan"
                assert restored.program_options == ["engine", "Eco50"]
                config = restored.configure_schedule({"instance_id": "1", "tariff_timezone": "Europe/London"})
                assert config["schedule_overnight_start"] == "21:00", "Original permission retains its window"
                assert restored.overnight_time("start") == "22:00", "Next-request setting survives restoration"
                assert restored._execution_task is None

                await restored.async_cancel()
                _, cancelled = fresh("cancelled", restored_path)
                await cancelled.async_load()
                assert cancelled.state["request"] is None
                assert cancelled.state["last_result"] == "cancelled"
                assert not cancelled.state["door_opened_since_last_cycle"]
                assert cancelled._execution_task is None

                expired_path, expired = fresh("expired", original_path)
                await expired.async_load()
                await expired._async_refresh_normal_request(now + timedelta(days=1))
                await expired._async_save()
                _, expired_again = fresh("expired-again", expired_path)
                await expired_again.async_load()
                assert expired_again.state["request"] is None
                assert expired_again.state["last_result"] == "expired"
                assert expired_again._execution_task is None
                print("Real disk restore: bounded request/settings retained; cancellation and expiry remain terminal; no device services called")
            finally:
                for hass in instances:
                    await hass.async_stop(force=True)


asyncio.run(main())
