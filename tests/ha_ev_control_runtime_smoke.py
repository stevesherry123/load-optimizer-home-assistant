"""Optional EV runtime end-to-end with mocked charger hardware and sources."""

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import yaml
from pathlib import Path
import tempfile
from unittest.mock import AsyncMock, patch

from ha_onboarding_smoke import Clock, ROOT, configure, identities
from homeassistant import loader
from homeassistant.bootstrap import async_from_config_dict
from homeassistant.components.http import HomeAssistantHTTP
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError


async def main():
    with tempfile.TemporaryDirectory(prefix="ev-control-runtime-") as directory:
        (Path(directory) / "custom_components").symlink_to(ROOT / "custom_components", target_is_directory=True)
        hass = HomeAssistant(directory)
        hass.config.skip_pip = True
        loader.async_setup(hass)
        Clock.current = datetime.now(timezone.utc)
        start = Clock.current - timedelta(minutes=7)
        commands = []
        notifications = []

        async def fake_switch(call):
            assert call.data["entity_id"] == "switch.synthetic_ev"
            commands.append(call.service)

        def reading(entity, value, attrs=None):
            hass.states.async_set(entity, value, attrs or {}, force_update=True)
            hass.states.get(entity).last_reported = Clock.current

        def refresh_inputs(switch="off", power=0, battery=20, cable="connected"):
            reading("switch.synthetic_ev", switch)
            reading("sensor.synthetic_ev_power", power, {"unit_of_measurement": "W"})
            reading("sensor.synthetic_ev_cable", cable)
            reading("sensor.synthetic_ev_battery", battery)

        examples = ROOT / "docs/examples"
        planning = yaml.safe_load((examples / "ev-planning.yaml").read_text())
        controls = yaml.safe_load((examples / "ev-switch-control.yaml").read_text())
        replacements = {
            "event.example_current_day_rates": "event.synthetic_today",
            "event.example_next_day_rates": "event.synthetic_tomorrow",
            "sensor.example_ev_battery": "sensor.synthetic_ev_battery",
            "sensor.example_ev_usable_capacity": "sensor.synthetic_capacity",
            "sensor.example_ev_cable": "sensor.synthetic_ev_cable",
            "switch.example_ev_power": "switch.synthetic_ev",
            "sensor.example_ev_wall_power": "sensor.synthetic_ev_power",
            "sensor.example_ev_charging_status": "sensor.synthetic_ev_status",
        }
        def replace(value):
            return [replace(item) for item in value] if isinstance(value, list) else replacements.get(value, value)
        planning = {key: replace(value) for key, value in planning.items()}
        controls = {key: replace(value) for key, value in controls.items()}
        settings = {**planning, **controls,
                    "ready_by": (Clock.current + timedelta(hours=1)).strftime("%H:%M")}
        rates = [{"start": start.isoformat(), "end": (start + timedelta(hours=2)).isoformat(), "value_inc_vat": 0.2}]
        with patch("custom_components.load_optimizer.price_cap.PriceCapManager.async_status", new=AsyncMock(return_value={"status": "not_configured"})), \
             patch("custom_components.load_optimizer.coordinator.datetime", Clock), \
             patch.object(HomeAssistantHTTP, "start", new=AsyncMock()), \
             patch.object(HomeAssistantHTTP, "stop", new=AsyncMock()):
            try:
                await async_from_config_dict({"homeassistant": {"time_zone": "Europe/London"}}, hass)
                await hass.async_start()
                from homeassistant.components.persistent_notification import async_register_callback
                unsubscribe_notifications = async_register_callback(hass, lambda action, values: notifications.append((action, values)))
                hass.services.async_register("switch", "turn_on", fake_switch)
                hass.services.async_register("switch", "turn_off", fake_switch)
                refresh_inputs()
                reading("sensor.synthetic_ev_status", "idle")
                reading("sensor.synthetic_capacity", 18)
                reading("event.synthetic_today", Clock.current.isoformat(), {"rates": rates})
                reading("event.synthetic_tomorrow", Clock.current.isoformat(), {"rates": []})
                advisory = await configure(hass, "ev_charging", "Guide advisory EV", {
                    **planning, "ready_by": settings["ready_by"],
                })
                advisory_coordinator = hass.data["load_optimizer"][advisory.entry_id]
                assert advisory_coordinator.data["plan"]["charging_mode"] == "required"
                assert not any(entity.startswith(("switch.", "button."))
                               for entity, device in identities(hass, advisory.entry_id).values())
                assert not commands
                entry = await configure(hass, "ev_charging", "Synthetic EV control", settings)
                coordinator = hass.data["load_optimizer"][entry.entry_id]
                ids = identities(hass, entry.entry_id)
                permission = ids[f"{entry.entry_id}_ev_control_enabled"][0]
                reconcile = ids[f"{entry.entry_id}_ev_reconcile_stopped"][0]
                assert not coordinator.ev_control_enabled and not commands
                assert coordinator.data["plan"]["charge_now"] and coordinator.data["tariff_source_issues"]
                assert hass.states.get(permission).state == "off"
                # Invoke entity methods through the actual registered entities,
                # rather than the fake hardware service registration.
                from homeassistant.helpers.entity_component import DATA_INSTANCES
                switch_component = hass.data[DATA_INSTANCES]["switch"]
                control = switch_component.get_entity(permission)
                button_component = hass.data[DATA_INSTANCES]["button"]
                recovery = button_component.get_entity(reconcile)
                await control.async_turn_on()
                assert commands == ["turn_on"]
                pinned = coordinator._ev_authorised_deadline
                assert coordinator.ev_adapter.session.phase == "starting"
                Clock.current += timedelta(seconds=19)
                refresh_inputs(switch="on", power=2343)
                await coordinator.async_refresh()
                await hass.async_block_till_done()
                assert coordinator.ev_adapter.session.phase == "charging" and commands == ["turn_on"]
                assert coordinator._ev_boundary_unsub is not None

                other = await configure(hass, "ev_charging", "Second synthetic EV", settings)
                other_coordinator = hass.data["load_optimizer"][other.entry_id]
                try:
                    await other_coordinator.async_set_ev_control(True)
                except HomeAssistantError:
                    pass
                else:
                    raise AssertionError("Two entries must not claim the same charger switch")
                assert not other_coordinator.ev_control_enabled and commands == ["turn_on"]

                # Invoke the exact scheduled boundary callback, which must refresh
                # directly even when ordinary source refreshes are debounced.
                with patch("custom_components.load_optimizer.coordinator.async_track_point_in_utc_time") as track:
                    coordinator._schedule_ev_boundary(coordinator.data["plan"], Clock.current)
                    callback, due_time = track.call_args.args[1:]
                Clock.current = due_time
                refresh_inputs(switch="on", power=2343)
                await callback(due_time)
                assert commands == ["turn_on"] and coordinator.ev_adapter.session.phase == "charging"

                # New battery readings immediately end owned charging at target.
                Clock.current += timedelta(seconds=20)
                refresh_inputs(switch="on", power=2343, battery=80)
                await coordinator.async_refresh()
                await hass.async_block_till_done()
                assert commands == ["turn_on", "turn_off"]
                Clock.current += timedelta(seconds=6)
                refresh_inputs(battery=80)
                await coordinator.async_refresh()
                assert coordinator.ev_adapter.session.phase == "idle"
                assert coordinator._ev_authorised_deadline == pinned

                # Permission and restored commands never resume silently on reload.
                assert await hass.config_entries.async_reload(entry.entry_id)
                await hass.async_block_till_done()
                try:
                    await control.async_turn_on()
                except HomeAssistantError:
                    pass
                else:
                    raise AssertionError("An unloaded controller cannot grant fresh permission")
                coordinator = hass.data["load_optimizer"][entry.entry_id]
                assert not coordinator.ev_control_enabled
                assert coordinator.ev_adapter.session.phase == "blocked"
                assert identities(hass, entry.entry_id) == ids
                switch_component = hass.data[DATA_INSTANCES]["switch"]
                button_component = hass.data[DATA_INSTANCES]["button"]
                control = switch_component.get_entity(permission)
                recovery = button_component.get_entity(reconcile)
                assert control.coordinator is coordinator
                await recovery.async_press()
                assert coordinator.ev_adapter.session.phase == "idle"

                Clock.current += timedelta(seconds=1)
                refresh_inputs(battery=20)
                await control.async_turn_on()
                assert commands[-1] == "turn_on" and len(commands) == 3, (commands, coordinator.data, coordinator.ev_adapter.status)
                Clock.current += timedelta(seconds=19)
                refresh_inputs(switch="on", power=2343)
                await coordinator.async_refresh()
                # Loss of future prices cuts owned power and never treats it as free.
                reading("event.synthetic_today", "unavailable", {"rates": rates})
                await coordinator.async_refresh()
                await hass.async_block_till_done()
                assert commands[-1] == "turn_off" and len(commands) == 4
                assert coordinator.data["plan"]["reason"] == "tariff_error"
                notification_id = f"load_optimizer_ev_control_{entry.entry_id}"
                assert any(notification_id in values and "prices" in values[notification_id]["message"] for action, values in notifications)
                Clock.current += timedelta(seconds=6)
                refresh_inputs()
                await control.async_turn_off()
                assert not coordinator.ev_control_enabled
                # A deadline that has passed stays passed for this control session.
                reading("event.synthetic_today", Clock.current.isoformat(), {"rates": rates})
                await recovery.async_press()
                await control.async_turn_on()
                deadline = coordinator._ev_authorised_deadline
                Clock.current = deadline + timedelta(seconds=1)
                refresh_inputs()
                count = len(commands)
                snapshot = await coordinator._async_ev_snapshot()
                assert snapshot["plan"]["reason"] == "deadline_passed"
                assert coordinator._ev_authorised_deadline == deadline
                await control.async_turn_off()
                assert len(commands) == count, "Expired deadline must not create another charging start"
                unsubscribe_notifications()
                print("Real HA EV runtime: forecast sources, opt-in off by default, metered start/target stop, precise boundary scheduling, tariff loss, pinned deadline, restart quarantine, reconciliation and stable identities passed")
            finally:
                await hass.async_stop(force=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
