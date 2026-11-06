"""Optional switch transport with durable reservations and metered confirmation.

This adapter has no registration side effects. Runtime wiring must explicitly
provide freshly recalculated plans and control permission; importing it never
enables hardware control.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
import math

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store

from .ev_control import EVControlSession


class EVSwitchAdapter:
    """Own only commands issued by this session, using power as delivery evidence."""

    def __init__(
        self, hass: HomeAssistant, entry_id: str, *, switch_entity: str,
        power_entity: str, connection_entity: str, status_entity: str | None = None,
        confirmation_seconds: int = 180,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        for entity_id, domains in ((switch_entity, ("switch",)), (power_entity, ("sensor",)),
                                   (connection_entity, ("sensor", "binary_sensor"))):
            if not isinstance(entity_id, str) or entity_id.partition(".")[0] not in domains or not entity_id.partition(".")[2]:
                raise ValueError("Charger controls require explicit switch, power and connection entities")
        self.hass = hass
        self.switch_entity = switch_entity
        self.power_entity = power_entity
        self.connection_entity = connection_entity
        self.status_entity = status_entity
        self.clock = clock
        self.session = EVControlSession(confirmation_seconds=confirmation_seconds)
        self.store = Store(hass, 1, f"load_optimizer.ev_control.{entry_id}")
        self._loaded = False
        self._lock = asyncio.Lock()
        self.reason = "control_disabled"

    async def _load(self) -> None:
        if not self._loaded:
            saved = await self.store.async_load()
            if saved is not None:
                timeout = self.session.confirmation_seconds
                self.session = EVControlSession.restored(saved if isinstance(saved, dict) else {})
                self.session.confirmation_seconds = timeout
            self._loaded = True

    @property
    def status(self) -> dict:
        messages = {
            "control_disabled": "Automatic charging is off.",
            "following_plan": "The charger is delivering power for this plan.",
            "awaiting_confirmation": "Waiting for the power meter to confirm the command.",
            "outside_active_plan": "No charging interval is active in the current usable plan.",
            "connection_not_verified": "The cable connection cannot be verified from a fresh reading.",
            "charging_state_unavailable": "The charger switch or power meter is unavailable, stale or inconclusive.",
            "external_power_not_owned": "The power switch was already on; this session will leave it alone.",
            "external_charging_not_owned": "Charging began outside this session and will be left alone.",
            "charging_stopped_externally": "Charging stopped unexpectedly. Review the charger before confirming it is stopped.",
            "restart_requires_reconciliation": "Automatic charging is off after reload. Verify stopped hardware and use Confirm Charging Stopped.",
            "confirmation_timeout": "The command was not confirmed in time. Automatic retries are blocked; review the charger.",
            "command_result_uncertain": "The command result is uncertain. Review the charger before reconciling; it will not be retried automatically.",
            "persistence_failed": "Control history could not be saved. Charging commands are blocked.",
            "preflight_changed": "Inputs changed before dispatch. No command was sent; verify stopped hardware before reconciling.",
            "reconciled_stopped": "Stopped hardware was verified. Automatic charging may be enabled again.",
            "delivery_requires_review": "Owned power was stopped after unexpected or unavailable delivery feedback. Review the charger and confirm stopped hardware before enabling again.",
            "car_feedback_blocked": "The configured car charging-status sensor is missing, unavailable or reporting an error.",
        }
        return {**self.session.checkpoint(), "reason": self.reason,
                "summary": messages.get(self.reason, "Review the charging state before enabling control."),
                "confirmation_seconds": self.session.confirmation_seconds,
                "feedback": "charger_power", "runtime_connected": False}

    async def _save(self) -> bool:
        try:
            await self.store.async_save(self.session.checkpoint())
        except (OSError, HomeAssistantError):
            self.session.phase = "blocked"
            self.reason = self.session.reason = "persistence_failed"
            return False
        return True

    def _fresh(self, state, now: datetime, seconds: int = 60) -> bool:
        timestamp = getattr(state, "last_reported", None)
        return bool(state and timestamp and timestamp.tzinfo is not None
                    and timedelta(0) <= now - timestamp <= timedelta(seconds=seconds))

    def _telemetry(self, now: datetime) -> dict:
        switch = self.hass.states.get(self.switch_entity)
        power = self.hass.states.get(self.power_entity)
        connection = self.hass.states.get(self.connection_entity)
        car = self.hass.states.get(self.status_entity) if self.status_entity else None
        watts = None
        if power and self._fresh(power, now):
            try:
                value = float(power.state)
                factor = {"W": 1, "kW": 1000}.get(power.attributes.get("unit_of_measurement"))
                if factor and math.isfinite(value) and 0 <= value <= 1000000:
                    watts = value * factor
            except (TypeError, ValueError, OverflowError):
                pass
        charging = None if watts is None or 20 < watts < 100 else watts >= 100
        connected = None
        if self._fresh(connection, now, seconds=300):
            if connection.state in {"connected", "on", "plugged_in"}:
                connected = True
            elif connection.state in {"disconnected", "off", "fault"}:
                connected = False
        switch_ok = bool(self._fresh(switch, now) and switch.state in {"on", "off"})
        # Volvo enum feedback is slower than the meter. idle/done cannot negate
        # positive measured delivery. A reported error is still a start blocker.
        # A fault must not clear merely because its unchanged reading ages.
        car_error = bool(self.status_entity and (not car or car.state in {"error", "unknown", "unavailable"}))
        return {"charging": charging, "connected": connected, "switch_ok": switch_ok,
                "switch_on": bool(switch and switch.state == "on"), "car_error": car_error,
                "fresh": switch_ok and charging is not None,
                "observed_at": power.last_reported if power else None}

    @staticmethod
    def _desired(snapshot: dict, now: datetime) -> bool:
        """Check actual intervals, never trust a remembered charge-now flag."""
        try:
            validated = snapshot.get("validated_at")
            if not isinstance(validated, datetime) or validated.tzinfo is None or not timedelta(0) <= now - validated <= timedelta(seconds=30):
                return False
            plan = snapshot["plan"]
            if plan.get("status") not in {"ready", "partial"} or plan.get("ready_to_charge") is not True:
                return False
            battery, target = float(plan["battery_percent"]), float(plan["target_percent"])
            if not all(math.isfinite(value) for value in (battery, target)) or not 0 <= battery < target <= 100:
                return False
            return any(datetime.fromisoformat(slot["start"]) <= now < datetime.fromisoformat(slot["end"])
                       for slot in plan.get("selected_slots", []))
        except (TypeError, ValueError, KeyError, OverflowError):
            return False

    def _can_start(self, snapshot: dict, telemetry: dict, now: datetime) -> bool:
        return bool(snapshot.get("enabled") is True and self._desired(snapshot, now)
                    and telemetry["connected"] is True and telemetry["fresh"]
                    and telemetry["charging"] is False and not telemetry["switch_on"]
                    and not telemetry["car_error"])

    async def async_step(self, snapshot_provider: Callable[[], Awaitable[dict]]) -> dict:
        """Revalidate twice, save before sending, and never retry an uncertain call."""
        async with self._lock:
            try:
                await self._load()
            except (OSError, HomeAssistantError):
                self.session.phase = "blocked"
                self.reason = "persistence_failed"
                return self.status
            snapshot = await snapshot_provider()
            now = self.clock()
            telemetry = self._telemetry(now)
            desired = self._desired(snapshot, now) and not telemetry["car_error"] and not self.session.requires_review
            if not self.session.owned and telemetry["switch_on"]:
                self.reason = "external_power_not_owned"
                return self.status
            before = self.session.checkpoint()
            wants_power = (snapshot.get("enabled") is True and desired and telemetry["connected"] is True)
            command = None
            if telemetry["switch_ok"] and telemetry["switch_on"]:
                delivery_lost = (self.session.phase == "charging" and (not telemetry["fresh"] or telemetry["charging"] is not True))
                if delivery_lost or telemetry["car_error"]:
                    command = self.session.stop_enabled_power(now, require_review=True)
                elif not wants_power:
                    command = self.session.stop_enabled_power(now)
            if command is None:
                confirmation_matches_switch = (not self.session.pending or telemetry["switch_on"]
                                               == (self.session.pending["action"] == "start"))
                command = self.session.evaluate(
                    now=now, enabled=snapshot.get("enabled") is True, desired=desired,
                    connected=telemetry["connected"],
                    charging=telemetry["charging"] if confirmation_matches_switch else None,
                    telemetry_fresh=telemetry["fresh"], observed_at=telemetry["observed_at"],
                )
            self.reason = self.session.reason
            if telemetry["car_error"] and snapshot.get("enabled") is True and self.session.phase == "idle":
                self.reason = self.session.reason = "car_feedback_blocked"
            if self.session.checkpoint() != before and not await self._save():
                return self.status
            if not command:
                return self.status
            # Persistence yields control. Recompute prices, target, permission,
            # time and inputs after it and immediately before the service call.
            snapshot = await snapshot_provider()
            now = self.clock()
            telemetry = self._telemetry(now)
            if command["action"] == "start":
                allowed = self._can_start(snapshot, telemetry, now)
            else:
                still_wanted = (snapshot.get("enabled") is True and self._desired(snapshot, now)
                                and telemetry["connected"] is True and not telemetry["car_error"]
                                and not self.session.requires_review)
                allowed = telemetry["switch_ok"] and telemetry["switch_on"] and not still_wanted
            if not allowed or now >= self.session.pending["deadline"]:
                self.session.phase = "blocked"
                self.reason = self.session.reason = "preflight_changed"
                await self._save()
                return self.status
            try:
                await self.hass.services.async_call(
                    "switch", "turn_on" if command["action"] == "start" else "turn_off",
                    {"entity_id": self.switch_entity}, blocking=True,
                )
            except (HomeAssistantError, OSError, TimeoutError):
                self.session.dispatch_failed(command["id"])
                self.reason = self.session.reason
                await self._save()
            return self.status

    async def async_reconcile_stopped(self) -> bool:
        """Explicit recovery is possible only with fresh switch-off and zero draw."""
        async with self._lock:
            await self._load()
            telemetry = self._telemetry(self.clock())
            if telemetry["switch_on"] or not telemetry["fresh"]:
                return False
            if not self.session.reconcile_stopped(charging=telemetry["charging"], telemetry_fresh=True):
                return False
            self.reason = self.session.reason
            return await self._save()
