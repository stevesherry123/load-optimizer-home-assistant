"""Data coordinator for Load Optimizer."""

from __future__ import annotations

from datetime import datetime, timezone
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
    CONF_READY_BY,
    CONF_SLOT_MINUTES,
    CONF_TARGET_PERCENT,
    CONF_TARGET_PERCENT_ENTITY,
    CONF_TARIFF_ENTITY,
    CONF_TARIFF_PRICE_UNIT,
    CONF_TARIFF_TIMEZONE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TARGET_PERCENT,
    DOMAIN,
)
from .optimizer.ev_charging import connection_is_available, deadline_from_ready_by, plan_ev_charge, state_float
from .optimizer.tariffs import tariff_periods_from_entity

LOGGER = logging.getLogger(__name__)


class LoadOptimizerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate one configured Load Optimizer load."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.config_entry = entry

    async def _async_update_data(self) -> dict[str, Any]:
        data = {**self.config_entry.data, **self.config_entry.options}
        now = datetime.now(timezone.utc)

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
