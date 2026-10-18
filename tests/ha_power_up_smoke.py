"""Minimum-HA calendar service, fresh free-price preflight and no-run precedence."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant import loader
from custom_components.load_optimizer.legacy_runtime import LegacyRuntime
from custom_components.load_optimizer.legacy import app_runtime as app


async def main():
    with tempfile.TemporaryDirectory() as config_dir:
        hass = HomeAssistant(config_dir)
        loader.async_setup(hass)
        try:
            hass.config.time_zone = "Europe/London"
            now = datetime.now(timezone.utc)
            event = {"start": now.isoformat(), "end": (now + timedelta(hours=1)).isoformat()}
            events = {"calendar.free": [event], "calendar.blocked": []}
            async def calendar_service(call):
                entity = call.data["entity_id"]
                return {entity: {"events": events[entity]}}
            hass.services.async_register("calendar", "get_events", calendar_service, supports_response=SupportsResponse.ONLY)
            for entity in events:
                hass.states.async_set(entity, "off")
            hass.states.async_set("sensor.power", "0")
            hass.states.async_set("sensor.rates", "ready", {"rates": [{
                "start": (now - timedelta(minutes=5)).isoformat(),
                "end": (now + timedelta(hours=4)).isoformat(), "price": 30}]})
            options = {"instances_yaml": json.dumps([{"id": "1", "power_sensor": "sensor.power",
                "program_policies": [{"program": "Quick45", "enabled": True, "allow_negative_price_run": True}]}]),
                "tariff_entity": "sensor.rates", "tariff_price_unit": "p_per_kwh",
                "free_window_entity": "calendar.free", "blocked_window_entity": "calendar.blocked"}
            runtime = LegacyRuntime(hass)
            instance = {}
            for _ in range(5):
                app.update_program_model(instance, {"program": "Quick45", "runtime_minutes": 30,
                    "energy_kwh": 0.7, "peak_power": 1400, "sample_count": 31,
                    "finish": (now - timedelta(days=1)).isoformat(),
                    "power_profile": [{"offset_seconds": 0, "power_w": 1400}, {"offset_seconds": 1800, "power_w": 1400}]})
            runtime.state = {"instances": {"1": instance}}
            request = {"mode": "negative_price", "program": "Quick45", "automatic": True,
                       "start": now.isoformat(), "finish": (now + timedelta(minutes=30)).isoformat()}
            before = deepcopy(runtime.state)
            assert await runtime.async_automatic_start_block(options, request) is None
            assert runtime.state == before
            events["calendar.free"] = []
            assert await runtime.async_automatic_start_block(options, request) == "power_hungry_window_outside_negative_price"
            events["calendar.free"] = [event]
            events["calendar.blocked"] = [event]
            assert await runtime.async_automatic_start_block(options, request) == "blocked_window_overlap"
            events["calendar.blocked"] = []
            hass.states.async_set("calendar.free", "unavailable")
            assert await runtime.async_automatic_start_block(options, request) == "free_window_source_unavailable"
            print("Real HA: Power Up grants zero-price eligibility; cancellation/unavailability veto; Power Down wins; learning unchanged")
        finally:
            await hass.async_stop(force=True)


asyncio.run(main())
