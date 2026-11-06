"""Real HA switch services with synthetic readings; no physical device I/O."""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from custom_components.load_optimizer.ev_switch_adapter import EVSwitchAdapter


async def main():
    with tempfile.TemporaryDirectory(prefix="ev-switch-adapter-") as directory:
        hass = HomeAssistant(directory)
        hass.config.skip_pip = True
        now = datetime(2026, 11, 4, 21, tzinfo=timezone.utc)
        enabled = True
        calls = []
        saved = []
        phase_during_call = []
        desired = True
        fail_service = False

        def reading(entity, value, unit=None):
            hass.states.async_set(entity, value, {"unit_of_measurement": unit} if unit else {}, force_update=True)
            hass.states.get(entity).last_reported = now

        def reset_readings():
            reading("switch.fake_ev", "off")
            reading("sensor.fake_power", 0, "W")
            reading("sensor.fake_cable", "connected")
            reading("sensor.fake_status", "idle")

        def adapter():
            item = EVSwitchAdapter(hass, "test", switch_entity="switch.fake_ev",
                                   power_entity="sensor.fake_power", connection_entity="sensor.fake_cable",
                                   status_entity="sensor.fake_status", clock=lambda: now)
            item.store = AsyncMock()
            item.store.async_load.return_value = None

            async def save(value):
                saved.append(deepcopy(value))
            item.store.async_save.side_effect = save
            return item

        async def snapshot():
            return {"enabled": enabled, "validated_at": now, "plan": {
                "status": "partial", "ready_to_charge": True, "charge_now": True,
                "battery_percent": 20, "target_percent": 80,
                "selected_slots": [{"start": (now - timedelta(minutes=1)).isoformat(),
                                    "end": (now + timedelta(minutes=1)).isoformat()}] if desired else [],
            }}

        async def service(call):
            calls.append((call.service, dict(call.data)))
            phase_during_call.append(saved[-1]["phase"])
            if fail_service:
                raise HomeAssistantError("Synthetic uncertain service result")

        hass.services.async_register("switch", "turn_on", service)
        hass.services.async_register("switch", "turn_off", service)
        try:
            reset_readings()
            item = adapter()
            # Concurrent refreshes cannot duplicate a reserved start.
            await asyncio.gather(item.async_step(snapshot), item.async_step(snapshot))
            assert calls == [("turn_on", {"entity_id": "switch.fake_ev"})]
            assert phase_during_call == ["starting"]
            assert item.session.phase == "starting", "Service success is not charging confirmation"

            now += timedelta(seconds=19)
            reading("switch.fake_ev", "on")
            reading("sensor.fake_power", 2.343, "kW")
            await item.async_step(snapshot)
            assert item.session.phase == "charging"
            # Slow Volvo idle/done feedback cannot override real measured power.
            now += timedelta(seconds=47)
            reading("sensor.fake_status", "done")
            reading("sensor.fake_power", 2343, "W")
            reading("switch.fake_ev", "on")
            await item.async_step(snapshot)
            assert item.session.phase == "charging" and len(calls) == 1

            enabled = False
            await item.async_step(snapshot)
            assert calls[-1][0] == "turn_off" and phase_during_call[-1] == "stopping"
            now += timedelta(seconds=6)
            reading("switch.fake_ev", "off")
            reading("sensor.fake_power", 0, "W")
            reading("sensor.fake_status", "charging")
            await item.async_step(snapshot)
            assert item.session.phase == "idle" and not item.session.owned

            # No external session is claimed, including switch-on with zero draw.
            enabled = True
            for watts in (0, 2343):
                item = adapter()
                reading("switch.fake_ev", "on")
                reading("sensor.fake_power", watts, "W")
                count = len(calls)
                await item.async_step(snapshot)
                assert len(calls) == count and not item.session.owned

            for invalid in ("unavailable", "nan", -1):
                reset_readings()
                item = adapter()
                reading("sensor.fake_power", invalid, "W")
                count = len(calls)
                await item.async_step(snapshot)
                assert len(calls) == count

            for car_state in ("error", "unavailable", "unknown"):
                reset_readings()
                item = adapter()
                reading("sensor.fake_status", car_state)
                hass.states.get("sensor.fake_status").last_reported = now - timedelta(hours=1)
                count = len(calls)
                await item.async_step(snapshot)
                assert len(calls) == count and item.reason == "car_feedback_blocked"

            # A persistence failure prevents dispatch, even when all inputs allow it.
            reset_readings()
            item = adapter()
            item.store.async_save.side_effect = OSError("Synthetic disk failure")
            count = len(calls)
            await item.async_step(snapshot)
            assert len(calls) == count and item.status["reason"] == "persistence_failed"

            # Tariff/permission/target data can change during a save; preflight wins.
            reset_readings()
            item = adapter()
            snapshots = 0
            async def changing_snapshot():
                nonlocal snapshots
                snapshots += 1
                result = await snapshot()
                if snapshots > 1:
                    result["plan"]["status"] = "not_ready"
                return result
            count = len(calls)
            await item.async_step(changing_snapshot)
            assert len(calls) == count and item.session.phase == "blocked"

            reset_readings()
            item = adapter()
            fail_service = True
            await item.async_step(snapshot)
            count = len(calls)
            fail_service = False
            await item.async_step(snapshot)
            assert len(calls) == count and item.session.phase == "blocked"

            # Stop an owned energised switch when demand ends even if the car
            # hasn't started drawing yet; do not leave power enabled indefinitely.
            reset_readings()
            item = adapter()
            await item.async_step(snapshot)
            now += timedelta(seconds=10)
            reading("switch.fake_ev", "on")
            reading("sensor.fake_power", 0, "W")
            desired = False
            await item.async_step(snapshot)
            assert calls[-1][0] == "turn_off" and item.session.phase == "stopping"
            now += timedelta(seconds=6)
            reading("switch.fake_ev", "off")
            reading("sensor.fake_power", 0, "W")
            await item.async_step(snapshot)
            assert not item.session.owned

            # Unexpected delivery loss cuts owned enabled power, then requires
            # review instead of turning it straight back on in the same slot.
            enabled = True
            desired = True
            reset_readings()
            item = adapter()
            await item.async_step(snapshot)
            now += timedelta(seconds=19)
            reading("switch.fake_ev", "on")
            reading("sensor.fake_power", 2343, "W")
            await item.async_step(snapshot)
            now += timedelta(seconds=10)
            reading("switch.fake_ev", "on")
            reading("sensor.fake_power", 0, "W")
            await item.async_step(snapshot)
            assert calls[-1][0] == "turn_off"
            now += timedelta(seconds=6)
            reading("switch.fake_ev", "off")
            reading("sensor.fake_power", 0, "W")
            await item.async_step(snapshot)
            count = len(calls)
            await item.async_step(snapshot)
            assert item.session.phase == "blocked" and len(calls) == count
            assert item.session.reason == "delivery_requires_review"

            # Meter zero alone cannot confirm that the switched supply is off.
            reset_readings()
            item = adapter()
            await item.async_step(snapshot)
            now += timedelta(seconds=10)
            reading("switch.fake_ev", "on")
            reading("sensor.fake_power", 0, "W")
            enabled = False
            await item.async_step(snapshot)
            now += timedelta(seconds=2)
            reading("sensor.fake_power", 0, "W")
            await item.async_step(snapshot)
            assert item.session.phase == "stopping" and item.session.owned

            # Even an unavailable meter cannot prevent an owned power cut when
            # the switch itself is fresh. Physical stop confirmation still waits.
            desired = True
            enabled = True
            reset_readings()
            item = adapter()
            await item.async_step(snapshot)
            now += timedelta(seconds=1)
            reading("switch.fake_ev", "on")
            reading("sensor.fake_power", "unavailable", "W")
            enabled = False
            await item.async_step(snapshot)
            assert calls[-1][0] == "turn_off"

            # A restored session never replays, and requires a verified stopped
            # switch and meter for explicit reconciliation.
            reset_readings()
            item = adapter()
            item.store.async_load.return_value = saved[-1]
            count = len(calls)
            await item.async_step(snapshot)
            assert item.session.phase == "blocked" and len(calls) == count
            reading("switch.fake_ev", "on")
            assert not await item.async_reconcile_stopped()
            reading("switch.fake_ev", "off")
            assert await item.async_reconcile_stopped()

            # A remembered charge-now value is insufficient outside a slot.
            enabled = True
            desired = False
            item = adapter()
            count = len(calls)
            await item.async_step(snapshot)
            assert len(calls) == count
            print("Real HA mocked switch adapter: metered confirmation, slow Volvo status, durable reservations, concurrent ticks, preflight changes, power cuts, persistence failures and explicit restart recovery passed")
        finally:
            await hass.async_stop(force=True)


if __name__ == "__main__":
    asyncio.run(main())
