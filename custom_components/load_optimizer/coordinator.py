"""Data coordinator for Load Optimizer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_BATTERY_CAPACITY_ENTITY,
    CONF_BATTERY_ENTITY,
    CONF_CHARGE_POWER_KW,
    CONF_CHARGER_EFFICIENCY,
    CONF_CONNECTION_STATUS_ENTITY,
    CONF_LOAD_TYPE,
    CONF_PRICE_CAP_PAYMENT_METHOD,
    CONF_PRICE_CAP_REGION,
    CONF_READY_BY,
    CONF_SCAN_INTERVAL,
    CONF_SLOT_MINUTES,
    CONF_TARGET_PERCENT,
    CONF_TARGET_PERCENT_ENTITY,
    CONF_TARIFF_ENTITY,
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
from .optimizer.tariffs import tariff_periods_from_entity
from .price_cap import PriceCapManager

LOGGER = logging.getLogger(__name__)


class LoadOptimizerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate one configured Load Optimizer load."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
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
        self.price_cap_manager = PriceCapManager(hass, entry)
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

    async def _async_update_data(self) -> dict[str, Any]:
        data = {**self.config_entry.data, **self.config_entry.options}
        now = datetime.now(timezone.utc)
        price_cap = await self.price_cap_manager.async_status(
            region=data.get(CONF_PRICE_CAP_REGION),
            payment_method=data.get(
                CONF_PRICE_CAP_PAYMENT_METHOD,
                DEFAULT_PRICE_CAP_PAYMENT_METHOD,
            ),
            timezone_name=data.get(CONF_TARIFF_TIMEZONE, DEFAULT_TARIFF_TIMEZONE),
            now_utc=now,
        )
        if data.get(CONF_LOAD_TYPE) == LOAD_TYPE_LEARNED_APPLIANCE:
            assert self.legacy_runtime is not None
            assert self.orchestration_migration is not None
            assert self.orchestrator is not None
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
            }

        tariff_entity = self._state_payload(data.get(CONF_TARIFF_ENTITY))
        try:
            periods = tariff_periods_from_entity(
                tariff_entity or {},
                reference_utc=now,
                timezone_name=data.get(CONF_TARIFF_TIMEZONE),
                price_unit=data.get(CONF_TARIFF_PRICE_UNIT),
            )
            tariff_error = None
        except (TypeError, ValueError) as error:
            periods = []
            tariff_error = str(error)

        battery_entity = self._state_payload(data.get(CONF_BATTERY_ENTITY))
        capacity_entity = self._state_payload(data.get(CONF_BATTERY_CAPACITY_ENTITY))
        target_entity = self._state_payload(data.get(CONF_TARGET_PERCENT_ENTITY))
        connection_entity = self._state_payload(data.get(CONF_CONNECTION_STATUS_ENTITY))

        target_percent = state_float(target_entity)
        if target_percent is None:
            target_percent = float(data.get(CONF_TARGET_PERCENT, DEFAULT_TARGET_PERCENT))

        deadline = deadline_from_ready_by(
            data.get(CONF_READY_BY),
            reference_utc=now,
            timezone_name=data.get(CONF_TARIFF_TIMEZONE),
        )
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
            connected=connection_is_available(connection_entity),
        )
        if tariff_error and plan.get("reason") == "no_tariff_periods":
            plan["reason"] = "tariff_error"
            plan["tariff_error"] = tariff_error
        return {
            "plan": plan,
            "tariff_period_count": len(periods),
            "last_updated": now.isoformat(),
            "price_cap": price_cap,
            "entities": {
                "tariff": data.get(CONF_TARIFF_ENTITY),
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
