"""Opt-in EV switch control; never adopt a manually started charging session."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import math

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .optimizer.ev_monitor import EVDeliveryMonitor, measurement


class EVChargeController:
    """Execute fresh plans with a durable ownership journal and restart disarm."""

    def __init__(self, hass, entry, publish):
        self.hass, self.entry, self.publish = hass, entry, publish
        self.store = Store(hass, 1, f"load_optimizer.ev_control.{entry.entry_id}")
        self.enabled = False
        self.owned_target = None
        self.plan = {}
        self.generated_at = None
        self.reason = "disabled"
        self.last_stop_reason = None
        self.session_started_at = None
        self.session_energy_start = None
        self._pending = None
        self._retry_after = None
        self._lock = asyncio.Lock()
        self._unsub = []
        self.monitor = EVDeliveryMonitor()

    @property
    def config(self):
        return {**self.entry.data, **self.entry.options}

    @property
    def status(self):
        return {"state": "enabled" if self.enabled else "disabled", "reason": self.reason,
                "charger_switch": self.config.get("ev_charger_switch"),
                "owns_charger": bool(self.owned_target), "pending_command": self._pending[0] if self._pending else None,
                "delivery": self.monitor.result,
                "last_stop_reason": self.last_stop_reason,
                "session_started_at": self.session_started_at.isoformat() if self.session_started_at else None,
                "session_max_hours": self.config.get("ev_session_max_hours", 24),
                "session_max_energy_kwh": self.config.get("ev_session_max_energy_kwh", 120),
                "session_energy_kwh": self._session_energy(),
                "plan_generated_at": self.generated_at.isoformat() if self.generated_at else None}

    def set_plan(self, plan, generated_at):
        self.plan, self.generated_at = plan, generated_at

    async def async_start(self):
        self.hass.data.setdefault("load_optimizer_ev_controls", {})[self.entry.entry_id] = self
        try:
            record = await self.store.async_load() or {}
            target = record.get("owned_target")
            if target and isinstance(target, str) and target.startswith("switch."):
                self.owned_target = target
        except Exception as error:
            self.reason = "ownership_storage_unavailable"
            raise HomeAssistantError("EV ownership journal could not be read; control was not started") from error
        self._unsub.append(async_track_time_interval(self.hass, self.async_tick, timedelta(seconds=10)))
        self._unsub.append(self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self.async_stop))
        await self.async_tick()

    async def async_stop(self, event=None):
        self.enabled = False
        await self.async_tick()
        for remove in self._unsub:
            remove()
        self._unsub.clear()
        self.hass.data.get("load_optimizer_ev_controls", {}).pop(self.entry.entry_id, None)

    async def async_enable(self):
        target = self.config.get("ev_charger_switch")
        if not isinstance(target, str) or not target.startswith("switch."):
            raise HomeAssistantError("Select a charger switch before enabling EV control")
        if not self.config.get("connection_status_entity"):
            raise HomeAssistantError("EV control requires an explicit vehicle connection sensor")
        if any(not self.config.get(key) for key in ("ev_charge_power_entity", "ev_charge_energy_entity", "ev_charging_status_entity")):
            raise HomeAssistantError("Configure charging power, cumulative energy and charging-status feedback first")
        if self.owned_target or self._pending:
            raise HomeAssistantError("Wait for the previous owned charging session to stop")
        state = self.hass.states.get(target)
        if state is None or state.state != "off":
            raise HomeAssistantError("The charger must be available and off before enabling control")
        self.monitor = EVDeliveryMonitor()
        self.last_stop_reason = None
        feedback = self._feedback()
        if feedback["energy"] is None:
            raise HomeAssistantError("A valid supply energy reading is required to begin a bounded session")
        self.session_started_at = datetime.now(timezone.utc)
        self.session_energy_start = feedback["energy"]
        self.enabled = True
        await self.async_tick()

    async def async_disable(self):
        self.enabled = False
        await self.async_tick()

    def _block(self, now):
        if not self.enabled:
            return "disabled"
        if not self.generated_at or not 0 <= (now - self.generated_at).total_seconds() <= 90:
            return "plan_stale"
        config = self.config
        try:
            hours = float(config.get("ev_session_max_hours", 24))
            energy_limit = float(config.get("ev_session_max_energy_kwh", 120))
            if not math.isfinite(hours) or not math.isfinite(energy_limit) or hours <= 0 or energy_limit <= 0:
                return "session_limits_invalid"
        except (ValueError, TypeError, OverflowError):
            return "session_limits_invalid"
        if self.session_started_at and (now - self.session_started_at).total_seconds() >= hours * 3600:
            return "session_duration_limit_reached"
        energy = self._session_energy()
        if energy is not None and energy < 0:
            return "energy_meter_reset"
        if energy is not None and energy >= energy_limit:
            return "session_energy_limit_reached"
        for other in self.hass.data.get("load_optimizer_ev_controls", {}).values():
            if other is not self and (other.enabled or other.owned_target) and other.config.get("ev_charger_switch") == config.get("ev_charger_switch"):
                return "charger_already_controlled"
        for key in ("battery_entity", "connection_status_entity", "ev_charge_power_entity", "ev_charge_energy_entity", "ev_charging_status_entity"):
            source = self.hass.states.get(config.get(key, ""))
            if source is None or source.state in {"unknown", "unavailable", ""}:
                return "telemetry_unavailable"
            timestamp = getattr(source, "last_reported", None) or source.last_updated
            if not 0 <= (now - timestamp).total_seconds() <= config.get("ev_telemetry_max_age_minutes", 15) * 60:
                return "telemetry_stale"
            if key == "connection_status_entity" and source.state.lower() not in {"connected", "charging", "plugged_in", "ready"}:
                return "vehicle_not_connected"
        try:
            battery = float(self.hass.states.get(config["battery_entity"]).state)
            target_entity = config.get("target_percent_entity")
            target_state = self.hass.states.get(target_entity) if target_entity else None
            target = float(target_state.state) if target_entity else float(config.get("target_percent", 100))
            if not math.isfinite(battery) or not math.isfinite(target) or not 0 <= battery <= 100 or not 0 < target <= 100:
                return "telemetry_invalid"
        except (AttributeError, ValueError, TypeError):
            return "telemetry_invalid"
        if battery >= target:
            return "target_reached"
        if self.plan.get("status") != "ready":
            return "plan_not_ready"
        feedback = self._feedback()
        if (feedback["capacity"] is None or not math.isfinite(feedback["capacity"]) or feedback["capacity"] <= 0
                or not math.isfinite(feedback["efficiency"]) or not 0.1 <= feedback["efficiency"] <= 1):
            return "delivery_inputs_invalid"
        if feedback["power"] is None or feedback["energy"] is None:
            return "feedback_units_or_values_invalid"
        if feedback["charging_status"] in {"error", "fault", "discharging"}:
            return "vehicle_charging_fault"
        return None

    def _session_energy(self):
        energy = measurement(self.hass.states.get(self.config.get("ev_charge_energy_entity", "")), "energy")
        if energy is None or self.session_energy_start is None:
            return None
        return round(energy - self.session_energy_start, 6)

    def _feedback(self):
        config = self.config
        def numeric(key):
            try:
                return float(self.hass.states.get(config.get(key, "")).state)
            except (AttributeError, TypeError, ValueError):
                return None
        status = self.hass.states.get(config.get("ev_charging_status_entity", ""))
        return {"battery": numeric("battery_entity"), "capacity": numeric("battery_capacity_entity"),
                "efficiency": float(config.get("charger_efficiency", 0.9)),
                "power": measurement(self.hass.states.get(config.get("ev_charge_power_entity", "")), "power"),
                "energy": measurement(self.hass.states.get(config.get("ev_charge_energy_entity", "")), "energy"),
                "charging_status": status.state.lower() if status else None}

    async def _journal(self, target):
        await self.store.async_save({"owned_target": target})
        self.owned_target = target

    async def _command(self, target, desired, now):
        # Journal intent before energising, so an interrupted start can be stopped on recovery.
        if desired == "on":
            await self._journal(target)
            if self._block(datetime.now(timezone.utc)):
                return
            feedback = self._feedback()
            self.monitor.start(now, feedback["battery"], feedback["energy"])
        if desired == "off":
            if self.last_stop_reason is None or self.reason != "disabled":
                self.last_stop_reason = self.reason
            self.monitor.record_totals(**self._feedback())
        self._pending = (desired, now)
        try:
            async with asyncio.timeout(10):
                await self.hass.services.async_call("switch", "turn_" + desired, {"entity_id": target}, blocking=True)
        except Exception:
            self.enabled = False
            self._pending = None
            self._retry_after = now + timedelta(seconds=60)
            self.reason = "command_failed"

    async def async_tick(self, ignored=None):
        async with self._lock:
            now = datetime.now(timezone.utc)
            try:
                if self._retry_after and now < self._retry_after:
                    return
                target = self.owned_target or self.config.get("ev_charger_switch")
                if not target:
                    self.reason = "charger_not_configured"
                    return
                state = self.hass.states.get(target)
                if state is None or state.state not in {"on", "off"}:
                    self.reason = "charger_unavailable"
                    return
                if self._pending:
                    desired, sent_at = self._pending
                    if state.state == desired:
                        self._pending = None
                        if desired == "off":
                            await self._journal(None)
                    elif now - sent_at < timedelta(seconds=20) and (desired != "on" or not self._block(now)):
                        self.reason = "awaiting_switch_confirmation"
                        return
                    else:
                        self.enabled = False
                        self._pending = None
                        self.reason = "switch_confirmation_failed"
                if self.owned_target and state.state == "off":
                    await self._journal(None)
                    self.enabled = False
                    self.reason = "manual_stop_or_restart_recovery"
                    return
                block = self._block(now)
                if block in {"session_duration_limit_reached", "session_energy_limit_reached",
                             "session_limits_invalid", "energy_meter_reset"}:
                    self.enabled = False
                    self.last_stop_reason = block
                selected_now = False
                if block is None:
                    try:
                        selected_now = any(datetime.fromisoformat(slot["start"]) <= now < datetime.fromisoformat(slot["end"])
                                           for slot in self.plan.get("selected_slots", []))
                    except (ValueError, TypeError, KeyError):
                        block = "invalid_plan"
                if not block and selected_now and self.owned_target and state.state == "on":
                    config = self.config
                    block = self.monitor.update(now, **self._feedback(),
                        minimum_power=config.get("ev_min_charging_power_w", 100),
                        confirmation_seconds=config.get("ev_charge_confirmation_seconds", 120),
                        tolerance_percent=config.get("ev_delivery_tolerance_percent", 30))
                    if block:
                        self.enabled = False
                if self.owned_target:
                    if block or not selected_now:
                        self.reason = block or "outside_selected_slot"
                        await self._command(target, "off", now)
                    else:
                        self.reason = "charging_in_selected_slot"
                elif state.state == "on":
                    self.enabled = False
                    self.reason = "manual_charging_not_owned"
                elif block:
                    self.reason = block
                elif selected_now:
                    self.reason = "starting_selected_slot"
                    await self._command(target, "on", now)
                else:
                    self.reason = "waiting_for_selected_slot"
            except Exception:
                self.enabled = False
                self.reason = "control_error"
            finally:
                self.publish()
