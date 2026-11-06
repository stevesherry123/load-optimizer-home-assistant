"""Real HA source changes during the final EV preflight never start old plans."""

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, patch

from ha_onboarding_smoke import Clock, ROOT, configure
from homeassistant import loader
from homeassistant.bootstrap import async_from_config_dict
from homeassistant.components.http import HomeAssistantHTTP
from homeassistant.core import HomeAssistant


async def main():
    with tempfile.TemporaryDirectory(prefix="ev-snapshot-races-") as directory:
        (Path(directory) / "custom_components").symlink_to(ROOT / "custom_components", target_is_directory=True)
        hass = HomeAssistant(directory)
        hass.config.skip_pip = True
        loader.async_setup(hass)
        Clock.current = datetime.now(timezone.utc)
        commands = []

        def reading(entity, value, attributes=None):
            hass.states.async_set(entity, value, attributes or {}, force_update=True)
            hass.states.get(entity).last_reported = Clock.current

        def prices(value, entity="event.race_prices"):
            reading(entity, Clock.current.isoformat(), {"rates": [{
                "start": (Clock.current - timedelta(minutes=10)).isoformat(),
                "end": (Clock.current + timedelta(hours=2)).isoformat(),
                "value_inc_vat": value,
            }]})

        def stopped():
            reading("switch.race_charger", "off")
            reading("sensor.race_power", 0, {"unit_of_measurement": "W"})
            reading("sensor.race_cable", "connected")

        async def service(call):
            commands.append((call.service, dict(call.data)))

        settings = {
            "tariff_entity": "event.race_prices", "tariff_price_unit": "gbp_per_kwh",
            "tariff_timezone": "Europe/London", "battery_entity": "sensor.race_battery",
            "battery_capacity_entity": "sensor.race_capacity", "target_percent": 80,
            "charge_power_kw": 2.3, "charger_efficiency": 0.9, "slot_minutes": 30,
            "connection_status_entity": "sensor.race_cable",
            "ev_charger_switch": "switch.race_charger", "ev_charge_power_entity": "sensor.race_power",
        }
        with patch("custom_components.load_optimizer.price_cap.PriceCapManager.async_status", new=AsyncMock(return_value={"status": "not_configured"})), \
             patch("custom_components.load_optimizer.coordinator.datetime", Clock), \
             patch.object(HomeAssistantHTTP, "start", new=AsyncMock()), \
             patch.object(HomeAssistantHTTP, "stop", new=AsyncMock()):
            try:
                await async_from_config_dict({"homeassistant": {"time_zone": "Europe/London"}}, hass)
                await hass.async_start()
                hass.services.async_register("switch", "turn_on", service)
                hass.services.async_register("switch", "turn_off", service)

                for scenario in ("battery", "target", "price", "additional_price"):
                    stopped()
                    reading("sensor.race_capacity", 18)
                    reading("sensor.race_battery", 20)
                    is_price = scenario in {"price", "additional_price"}
                    prices(-0.1 if is_price else 0.2)
                    reading("sensor.race_target", 80)
                    extra = {}
                    if scenario == "target":
                        extra["target_percent_entity"] = "sensor.race_target"
                    if scenario == "additional_price":
                        reading("event.race_prices", "0.2")  # Current-price-only primary.
                        prices(-0.1, "event.race_extra_prices")
                        extra["tariff_entities"] = ["event.race_extra_prices"]
                    entry = await configure(hass, "ev_charging", "Preflight race " + scenario, {
                        **settings, **extra, "charging_mode": "opportunistic" if is_price else "required",
                        "maximum_price_p_per_kwh": 0,
                    })
                    coordinator = hass.data["load_optimizer"][entry.entry_id]
                    original = coordinator._async_ev_plan
                    calculations = 0

                    async def change_after_final_calculation(*args, **kwargs):
                        nonlocal calculations
                        result = await original(*args, **kwargs)
                        calculations += 1
                        # Outer update, first adapter snapshot, then the final
                        # pre-dispatch snapshot after the durable reservation.
                        if calculations == 3:
                            if scenario == "battery":
                                reading("sensor.race_battery", 80)
                            elif scenario == "target":
                                reading("sensor.race_target", 20)
                            elif scenario == "additional_price":
                                prices(0.2, "event.race_extra_prices")
                            else:
                                prices(0.2)
                        return result

                    with patch.object(coordinator, "_async_ev_plan", side_effect=change_after_final_calculation), \
                         patch.object(coordinator, "async_request_refresh", new=AsyncMock()):
                        await coordinator.async_set_ev_control(True)
                    assert calculations >= 4, "Changed final sources require recalculation"
                    assert not commands, (scenario, commands)
                    assert coordinator.ev_adapter.session.phase == "blocked"
                    expected = "target_already_met" if scenario in {"battery", "target"} else "no_slots_below_price_ceiling"
                    assert coordinator.data["plan"]["reason"] == expected, coordinator.data["plan"]
                    await coordinator.async_set_ev_control(False)
                    stopped()
                    await coordinator.async_reconcile_ev()

                await hass.async_block_till_done()

                # Capacity is part of the same input set, even though it is not
                # required to refresh at the meter's reporting frequency.
                original = coordinator._async_ev_plan
                calculations = 0
                reading("sensor.race_battery", 20)
                await hass.async_block_till_done()

                async def change_capacity_once(*args, **kwargs):
                    nonlocal calculations
                    result = await original(*args, **kwargs)
                    calculations += 1
                    if calculations == 1:
                        reading("sensor.race_capacity", 24)
                    return result

                with patch.object(coordinator, "_async_ev_plan", side_effect=change_capacity_once), \
                     patch.object(coordinator, "async_request_refresh", new=AsyncMock()):
                    snapshot = await coordinator._async_ev_snapshot()
                assert calculations == 2, (calculations, snapshot)
                assert snapshot["plan"]["needed_battery_kwh"] == 14.4

                # Continuous updates cannot make the final check loop forever or
                # allow a plan assembled from inconsistent generations.
                await hass.async_block_till_done()
                calculations = 0

                async def always_change(*args, **kwargs):
                    nonlocal calculations
                    result = await original(*args, **kwargs)
                    calculations += 1
                    reading("sensor.race_battery", 20 if calculations % 2 else 21)
                    return result

                with patch.object(coordinator, "_async_ev_plan", side_effect=always_change), \
                     patch.object(coordinator, "async_request_refresh", new=AsyncMock()):
                    snapshot = await coordinator._async_ev_snapshot()
                assert calculations == 3
                assert snapshot["plan"]["reason"] == "control_inputs_changing"
                assert not commands
                print("Real HA EV preflight: late target completion and price-ceiling changes prevent dispatch; capacity changes recalculate; continuous churn stops after three attempts")
            finally:
                await hass.async_stop(force=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
