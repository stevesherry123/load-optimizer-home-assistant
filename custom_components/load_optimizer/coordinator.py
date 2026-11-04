"""Data coordinator for Load Optimizer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from functools import partial
import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_BATTERY_CAPACITY_ENTITY,
    CONF_BATTERY_ENTITY,
    CONF_CHARGE_POWER_KW,
    CONF_CHARGING_MODE,
    CONF_MAXIMUM_PRICE,
    DEFAULT_CHARGING_MODE,
    DEFAULT_MAXIMUM_PRICE,
    CONF_CHARGER_EFFICIENCY,
    CONF_CONNECTION_STATUS_ENTITY,
    CONF_EV_CHARGER_SWITCH,
    CONF_EV_POWER_ENTITY,
    CONF_EV_STATUS_ENTITY,
    CONF_EV_CONFIRMATION_SECONDS,
    CONF_LOAD_TYPE,
    CONF_PRICE_CAP_PAYMENT_METHOD,
    CONF_PRICE_CAP_REGION,
    CONF_READY_BY,
    CONF_SCAN_INTERVAL,
    CONF_SLOT_MINUTES,
    CONF_TARGET_PERCENT,
    CONF_TARGET_PERCENT_ENTITY,
    CONF_TARIFF_ENTITY,
    CONF_TARIFF_ENTITIES,
    CONF_TARIFF_PRICE_UNIT,
    CONF_TARIFF_TIMEZONE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_PRICE_CAP_PAYMENT_METHOD,
    DEFAULT_TARIFF_TIMEZONE,
    DEFAULT_TARGET_PERCENT,
    DOMAIN,
    LOAD_TYPE_LEARNED_APPLIANCE,
)
from .legacy_runtime import LegacyRuntime
from .orchestration import NativeOrchestrator
from .orchestration_migration import OrchestrationMigration
from .optimizer.ev_charging import connection_is_available, deadline_from_ready_by, plan_ev_charge, state_float
from .optimizer.ev_sources import ev_tariff_periods
from .price_cap import PriceCapManager
from .tariff_intelligence import get_service
from .narrative import OptionalNarrative
from .ev_switch_adapter import EVSwitchAdapter

LOGGER = logging.getLogger(__name__)


class LoadOptimizerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate one configured Load Optimizer load."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, *, local_timezone: tzinfo) -> None:
        data = {**entry.data, **entry.options}
        update_interval = DEFAULT_SCAN_INTERVAL
        if data.get(CONF_LOAD_TYPE) == LOAD_TYPE_LEARNED_APPLIANCE:
            update_interval = timedelta(seconds=int(data.get(CONF_SCAN_INTERVAL, 60)))
        super().__init__(
            hass,
            LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=update_interval,
        )
        self.config_entry = entry
        self.ev_adapter = None
        self.ev_control_enabled = False
        self._ev_authorised_deadline = None
        self._ev_boundary_unsub = None
        self._ev_notification_reason = None
        self._ev_snapshot_reason = None
        self._ev_latest_plan = None
        self._ev_permission_lock = asyncio.Lock()
        self._ev_closed = False
        if data.get(CONF_LOAD_TYPE) != LOAD_TYPE_LEARNED_APPLIANCE and all(data.get(key) for key in (
            CONF_EV_CHARGER_SWITCH, CONF_EV_POWER_ENTITY, CONF_CONNECTION_STATUS_ENTITY,
        )):
            self.ev_adapter = EVSwitchAdapter(
                hass, entry.entry_id, switch_entity=data[CONF_EV_CHARGER_SWITCH],
                power_entity=data[CONF_EV_POWER_ENTITY], connection_entity=data[CONF_CONNECTION_STATUS_ENTITY],
                status_entity=data.get(CONF_EV_STATUS_ENTITY),
                confirmation_seconds=int(data.get(CONF_EV_CONFIRMATION_SECONDS, 180)),
                clock=lambda: datetime.now(timezone.utc),
            )
            self.update_interval = timedelta(seconds=30)
        self.local_timezone = local_timezone
        self.price_cap_manager = PriceCapManager(hass, entry)
        self.tariff_intelligence = get_service(hass, data)
        self.narrative = OptionalNarrative(hass, self.async_publish_narrative)
        self.legacy_runtime = LegacyRuntime(hass) if data.get(CONF_LOAD_TYPE) == LOAD_TYPE_LEARNED_APPLIANCE else None
        self.orchestration_migration = (
            OrchestrationMigration(hass, entry)
            if data.get(CONF_LOAD_TYPE) == LOAD_TYPE_LEARNED_APPLIANCE
            else None
        )
        self.orchestrator = (
            NativeOrchestrator(hass, entry, self.orchestration_migration)
            if self.orchestration_migration is not None
            else None
        )
        if self.legacy_runtime and self.orchestrator:
            self.legacy_runtime.external_state_provider = self._orchestration_legacy_state
            self.orchestrator.set_automatic_preflight(self._async_automatic_start_block)
            self.legacy_runtime.schedule_config_provider = self.orchestrator.configure_schedule

    async def _async_automatic_start_block(self, request: dict[str, Any]) -> str | None:
        if self.legacy_runtime is None:
            return "automatic_configuration_unavailable"
        options = {**self.config_entry.data, **self.config_entry.options}
        return await self.legacy_runtime.async_automatic_start_block(options, request)

    async def _async_ev_snapshot(self) -> dict:
        data = {**self.config_entry.data, **self.config_entry.options}
        now = datetime.now(timezone.utc)
        result = await self._async_ev_plan(data, now, deadline_override=self._ev_authorised_deadline)
        # Control cannot fall back to an old or missing configured target/battery
        # even though advisory planning may still display its configured fallback.
        for key in (CONF_BATTERY_ENTITY, CONF_TARGET_PERCENT_ENTITY):
            entity_id = data.get(key)
            if not entity_id:
                continue
            state = self.hass.states.get(entity_id)
            fresh = (state and timedelta(0) <= now - state.last_reported <= timedelta(minutes=5))
            if state_float(self._state_payload(entity_id)) is None or not fresh:
                result["plan"] = {"status": "not_ready", "reason": "control_source_unavailable"}
        self._ev_snapshot_reason = result["plan"].get("reason")
        self._ev_latest_plan = result["plan"]
        return {"enabled": self.ev_control_enabled and not self._ev_closed,
                "validated_at": now, "plan": result["plan"]}

    async def async_set_ev_control(self, enabled: bool) -> None:
        async with self._ev_permission_lock:
            if self._ev_closed:
                raise HomeAssistantError("This charging controller has been unloaded")
            await self._async_set_ev_control(enabled)

    async def _async_set_ev_control(self, enabled: bool) -> None:
        if not self.ev_adapter:
            raise HomeAssistantError("Configure the charger switch, power meter and cable connection first")
        owners = self.hass.data.setdefault(f"{DOMAIN}_ev_switch_owners", {})
        entity = self.ev_adapter.switch_entity
        if enabled and owners.get(entity) not in (None, self.config_entry.entry_id):
            raise HomeAssistantError("Another EV entry already controls this charger switch")
        if enabled:
            if not self.ev_control_enabled:
                data = {**self.config_entry.data, **self.config_entry.options}
                self._ev_authorised_deadline = await self.hass.async_add_executor_job(partial(
                    deadline_from_ready_by, data.get(CONF_READY_BY),
                    reference_utc=datetime.now(timezone.utc),
                    timezone_name=data.get(CONF_TARIFF_TIMEZONE, DEFAULT_TARIFF_TIMEZONE),
                ))
            # Another entry may have claimed the same switch while the timezone
            # lookup yielded. Check again at the actual ownership assignment.
            if self._ev_closed:
                raise HomeAssistantError("This charging controller has been unloaded")
            if owners.get(entity) not in (None, self.config_entry.entry_id):
                raise HomeAssistantError("Another EV entry already controls this charger switch")
            owners[entity] = self.config_entry.entry_id
        self.ev_control_enabled = enabled
        # Disable goes directly to the adapter; no supplier/network refresh can
        # hold up an owned power cut. Full refresh then publishes its result.
        if not enabled:
            await self.ev_adapter.async_step(self._async_ev_snapshot)
        await self.async_refresh()

    async def async_reconcile_ev(self) -> None:
        async with self._ev_permission_lock:
            if self._ev_closed:
                raise HomeAssistantError("This charging controller has been unloaded")
            await self._async_reconcile_ev()

    async def _async_reconcile_ev(self) -> None:
        if not self.ev_adapter or self.ev_control_enabled:
            raise HomeAssistantError("Turn automatic charging off before reconciling")
        if not await self.ev_adapter.async_reconcile_stopped():
            raise HomeAssistantError("Reconciliation needs a fresh off switch and stopped power meter")
        self._release_ev_owner_if_stopped()
        await self.async_refresh()

    def _release_ev_owner_if_stopped(self) -> None:
        if self.ev_control_enabled or not self.ev_adapter or self.ev_adapter.session.owned or self.ev_adapter.session.pending:
            return
        owners = self.hass.data.get(f"{DOMAIN}_ev_switch_owners", {})
        if owners.get(self.ev_adapter.switch_entity) == self.config_entry.entry_id:
            owners.pop(self.ev_adapter.switch_entity, None)

    def _schedule_ev_boundary(self, plan: dict, now: datetime) -> None:
        if self._ev_boundary_unsub:
            self._ev_boundary_unsub()
            self._ev_boundary_unsub = None
        if self._ev_closed:
            return
        times = []
        for slot in plan.get("selected_slots", []):
            for key in ("start", "end"):
                value = datetime.fromisoformat(slot[key])
                if value > now:
                    times.append(value)
        if self.ev_adapter.session.pending:
            deadline = self.ev_adapter.session.pending["deadline"]
            if deadline > now:
                times.append(deadline)
        if times:
            async def due(_now):
                await self.async_refresh()
            self._ev_boundary_unsub = async_track_point_in_utc_time(self.hass, due, min(times))

    async def async_stop_ev(self) -> None:
        self._ev_closed = True
        async with self._ev_permission_lock:
            await self._async_stop_ev()

    async def _async_stop_ev(self) -> None:
        if self.ev_adapter:
            self.ev_control_enabled = False
            await self.ev_adapter.async_step(self._async_ev_snapshot)
            if self._ev_boundary_unsub:
                self._ev_boundary_unsub()
                self._ev_boundary_unsub = None
            self._release_ev_owner_if_stopped()

    async def _async_update_data(self) -> dict[str, Any]:
        data = {**self.config_entry.data, **self.config_entry.options}
        now = datetime.now(timezone.utc)
        price_cap = await self.price_cap_manager.async_status(
            region=data.get(CONF_PRICE_CAP_REGION),
            payment_method=data.get(
                CONF_PRICE_CAP_PAYMENT_METHOD,
                DEFAULT_PRICE_CAP_PAYMENT_METHOD,
            ),
            local_timezone=self.local_timezone,
            now_utc=now,
        )
        intelligence = await self.tariff_intelligence.async_status(price_cap, now)
        intelligence["narrative"] = self.narrative.snapshot(intelligence)
        if data.get(CONF_LOAD_TYPE) == LOAD_TYPE_LEARNED_APPLIANCE:
            if self.legacy_runtime is None or self.orchestration_migration is None or self.orchestrator is None:
                raise RuntimeError("Learned-appliance runtime was not initialized")
            await self.orchestration_migration.async_load()
            await self.orchestrator.async_load()
            result = await self.legacy_runtime.async_scan(data)
            return {
                "mode": LOAD_TYPE_LEARNED_APPLIANCE,
                "status": result.status,
                "instance_count": result.instance_count,
                "published_entity_count": result.entity_count,
                "legacy_entities": result.entities,
                "legacy_instances": result.instances,
                "last_scan": result.last_scan,
                "message": result.message,
                "orchestration_migration": self.orchestration_migration.status,
                "orchestration": self.orchestrator.status,
                "price_cap": price_cap,
                "tariff_intelligence": intelligence,
            }

        result = await self._async_ev_plan(data, now, deadline_override=self._ev_authorised_deadline)
        result.update({"price_cap": price_cap, "tariff_intelligence": intelligence})
        if self.ev_adapter:
            result["control"] = {**await self.ev_adapter.async_step(self._async_ev_snapshot),
                                 "enabled": self.ev_control_enabled, "runtime_connected": True}
            if self.ev_control_enabled and self._ev_latest_plan is not None:
                result["plan"] = self._ev_latest_plan
            result["control"]["plan_reason"] = self._ev_snapshot_reason
            result["plan"]["advisory_only"] = not self.ev_control_enabled
            if self.ev_control_enabled and self._ev_snapshot_reason == "control_source_unavailable" and result["control"]["phase"] != "blocked":
                result["control"]["summary"] = "Battery or target feedback is missing, invalid or stale. New charging is blocked. Review existing power and restore fresh readings."
            self._release_ev_owner_if_stopped()
            self._schedule_ev_boundary(result["plan"], now)
            await self._async_ev_notify(result)
        else:
            result["control"] = {"phase": "advisory", "enabled": False,
                                 "reason": "charger_control_not_configured"}
        return result

    async def _async_ev_notify(self, result: dict) -> None:
        control = result["control"]
        reason = None
        summary = control["summary"]
        if self.ev_control_enabled or control.get("owned"):
            if control["phase"] == "blocked":
                reason = control["reason"]
                if result["plan"].get("reason") == "tariff_error":
                    summary += " Future charging prices are also unavailable."
            elif result["plan"].get("reason") == "tariff_error":
                reason = "tariff_error"
                summary = "Future charging prices are unavailable. No new unpriced charging will start; review the EV tariff sources."
            elif control.get("plan_reason") == "control_source_unavailable":
                reason = "control_source_unavailable"
            elif control["reason"] in {"charging_state_unavailable", "car_feedback_blocked"}:
                reason = control["reason"]
        if reason == self._ev_notification_reason:
            return
        notification_id = f"{DOMAIN}_ev_control_{self.config_entry.entry_id}"
        if reason and self.hass.services.has_service("persistent_notification", "create"):
            await self.hass.services.async_call("persistent_notification", "create", {
                "notification_id": notification_id, "title": f"{self.config_entry.title}: charging needs attention",
                "message": summary,
            }, blocking=True)
        elif self._ev_notification_reason and self.hass.services.has_service("persistent_notification", "dismiss"):
            await self.hass.services.async_call("persistent_notification", "dismiss", {
                "notification_id": notification_id,
            }, blocking=True)
        self._ev_notification_reason = reason

    async def _async_ev_plan(self, data: dict, now: datetime, *, deadline_override: datetime | None = None) -> dict:
        """Recalculate from current source states without sending commands."""
        additional = data.get(CONF_TARIFF_ENTITIES) or []
        if isinstance(additional, str):
            additional = [entity_id.strip() for entity_id in additional.split(",") if entity_id.strip()]
        source_ids = [data.get(CONF_TARIFF_ENTITY)] + list(additional)
        source_ids = list(dict.fromkeys(entity_id for entity_id in source_ids if entity_id))
        try:
            periods, tariff_source_issues = await self.hass.async_add_executor_job(partial(ev_tariff_periods,
                [self._state_payload(entity_id) for entity_id in source_ids],
                reference_utc=now,
                timezone_name=data.get(CONF_TARIFF_TIMEZONE),
                price_unit=data.get(CONF_TARIFF_PRICE_UNIT),
            ))
            tariff_error = None
        except (TypeError, ValueError) as error:
            periods = []
            tariff_source_issues = []
            tariff_error = str(error)

        battery_entity = self._state_payload(data.get(CONF_BATTERY_ENTITY))
        capacity_entity = self._state_payload(data.get(CONF_BATTERY_CAPACITY_ENTITY))
        target_entity = self._state_payload(data.get(CONF_TARGET_PERCENT_ENTITY))
        connection_entity = self._state_payload(data.get(CONF_CONNECTION_STATUS_ENTITY))

        target_percent = state_float(target_entity)
        if target_percent is None:
            target_percent = float(data.get(CONF_TARGET_PERCENT, DEFAULT_TARGET_PERCENT))

        try:
            deadline = deadline_override or await self.hass.async_add_executor_job(partial(deadline_from_ready_by,
                data.get(CONF_READY_BY), reference_utc=now,
                timezone_name=data.get(CONF_TARIFF_TIMEZONE),
            ))
        except (TypeError, ValueError):
            plan = {"status": "not_ready", "reason": "invalid_ready_by",
                    "summary": "The local charging deadline could not be resolved. Review Ready by and tariff timezone.",
                    "charging_mode": data.get(CONF_CHARGING_MODE, DEFAULT_CHARGING_MODE),
                    "target_reachable": False, "advisory_only": True, "cost_basis": "electricity_only",
                    "ready_to_charge": False, "charge_now": False, "selected_slots": []}
        else:
            plan = plan_ev_charge(
                periods=periods,
                battery_percent=state_float(battery_entity),
                battery_capacity_kwh=state_float(capacity_entity),
                charge_power_kw=float(data.get(CONF_CHARGE_POWER_KW)),
                target_percent=target_percent,
                charger_efficiency=float(data.get(CONF_CHARGER_EFFICIENCY)),
                slot_minutes=int(data.get(CONF_SLOT_MINUTES)),
                reference_utc=now,
                deadline_utc=deadline,
                connected=connection_is_available(connection_entity) and (
                    not data.get(CONF_CONNECTION_STATUS_ENTITY) or connection_entity is not None),
                charging_mode=data.get(CONF_CHARGING_MODE, DEFAULT_CHARGING_MODE),
                maximum_price_p_per_kwh=data.get(CONF_MAXIMUM_PRICE, DEFAULT_MAXIMUM_PRICE),
            )
        if tariff_error and plan.get("reason") == "no_tariff_periods":
            plan["reason"] = "tariff_error"
            plan["tariff_error"] = tariff_error
        return {
            "plan": plan,
            "tariff_period_count": len(periods),
            "tariff_source_issues": tariff_source_issues,
            "last_updated": now.isoformat(),
            "entities": {
                "tariff": data.get(CONF_TARIFF_ENTITY),
                "additional_tariffs": data.get(CONF_TARIFF_ENTITIES) or [],
                "battery": data.get(CONF_BATTERY_ENTITY),
                "battery_capacity": data.get(CONF_BATTERY_CAPACITY_ENTITY),
                "target_percent": data.get(CONF_TARGET_PERCENT_ENTITY),
                "connection_status": data.get(CONF_CONNECTION_STATUS_ENTITY),
            },
        }

    def _state_payload(self, entity_id: str | None) -> dict[str, Any] | None:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        return {
            "state": state.state,
            "attributes": dict(state.attributes),
            "entity_id": entity_id,
        }

    def _orchestration_legacy_state(self, entity_id: str) -> dict[str, Any] | None:
        if not self.orchestrator or not self.orchestrator.state.get("active"):
            return None
        return self.orchestrator.legacy_state(entity_id)

    def async_update_orchestration_data(self, status: dict[str, Any]) -> None:
        """Publish orchestration changes between optimizer scans."""
        if self.data is None:
            return
        self.data["orchestration"] = status
        self.async_update_listeners()

    def async_publish_narrative(self):
        """Publish AI lifecycle changes independently of scheduled analysis."""
        if self.data:
            analysis = self.data.get("tariff_intelligence", {})
            analysis["narrative"] = self.narrative.snapshot(analysis)
            self.async_update_listeners()
