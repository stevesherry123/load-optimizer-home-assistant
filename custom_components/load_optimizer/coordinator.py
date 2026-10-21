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
    CONF_CONNECTION_STATUS_ENTITY,
    CONF_LOAD_TYPE,
    CONF_PRICE_CAP_PAYMENT_METHOD,
    CONF_PRICE_CAP_REGION,
    CONF_SCAN_INTERVAL,
    CONF_TARGET_PERCENT_ENTITY,
    CONF_TARIFF_ENTITY,
    CONF_TARIFF_ENTITIES,
    CONF_TARIFF_TIMEZONE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_PRICE_CAP_PAYMENT_METHOD,
    DEFAULT_TARIFF_TIMEZONE,
    DOMAIN,
    LOAD_TYPE_LEARNED_APPLIANCE,
)
from .legacy_runtime import LegacyRuntime
from .orchestration import NativeOrchestrator
from .orchestration_migration import OrchestrationMigration
from .optimizer.ev_setup import build_ev_plan, tariff_entities
from .price_cap import PriceCapManager
from .tariff_intelligence import get_service
from .narrative import OptionalNarrative
from .ev_control import EVChargeController
from .optimizer.ev_review import review_snapshot

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
        self.ev_controller = (EVChargeController(hass, entry, self._publish_ev_control)
                              if data.get(CONF_LOAD_TYPE) != LOAD_TYPE_LEARNED_APPLIANCE and data.get("ev_charger_switch") else None)
        if self.ev_controller and data.get("ev_charger_switch"):
            self.update_interval = timedelta(seconds=30)
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

    async def _async_automatic_start_block(self, request: dict[str, Any]) -> str | None:
        if self.legacy_runtime is None:
            return "automatic_configuration_unavailable"
        options = {**self.config_entry.data, **self.config_entry.options}
        return await self.legacy_runtime.async_automatic_start_block(options, request)

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

        sources = {entity_id: self._state_payload(entity_id) for entity_id in tariff_entities(data)}
        for key in (CONF_BATTERY_ENTITY, CONF_BATTERY_CAPACITY_ENTITY, CONF_TARGET_PERCENT_ENTITY, CONF_CONNECTION_STATUS_ENTITY):
            if data.get(key):
                sources[data[key]] = self._state_payload(data[key])
        plan, periods = build_ev_plan(data, sources, now)
        if self.ev_controller:
            self.ev_controller.set_plan(plan, now)
        review_sources = {entity_id: self._state_payload(entity_id) for key, entity_id in data.items()
                          if key.endswith("_entity") or key == "ev_charger_switch" if isinstance(entity_id, str) and entity_id}
        review = review_snapshot(data, plan, periods, review_sources,
                                 self.ev_controller.status if self.ev_controller else None, now)
        return {
            "plan": plan,
            "ev_review": review,
            "tariff_period_count": len(periods),
            "last_updated": now.isoformat(),
            "price_cap": price_cap,
            "tariff_intelligence": intelligence,
            "entities": {
                "tariff": data.get(CONF_TARIFF_ENTITY),
                "additional_tariffs": data.get(CONF_TARIFF_ENTITIES, ""),
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
            "last_reported": (getattr(state, "last_reported", None) or state.last_updated).isoformat(),
        }

    def _publish_ev_control(self):
        if self.data and self.ev_controller and "ev_review" in self.data:
            self.data["ev_review"]["control"] = self.ev_controller.status
        self.async_update_listeners()

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
