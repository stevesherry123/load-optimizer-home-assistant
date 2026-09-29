"""Native orchestration date/time controls."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_LOAD_TYPE, DOMAIN, LOAD_TYPE_LEARNED_APPLIANCE
from .coordinator import LoadOptimizerCoordinator
from .orchestration_entity import OrchestrationEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if entry.data.get(CONF_LOAD_TYPE) != LOAD_TYPE_LEARNED_APPLIANCE:
        return
    coordinator: LoadOptimizerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            NativeOrchestrationDateTime(
                coordinator,
                "special_price_window_start",
                "Special Price Window Start",
            ),
            NativeOrchestrationDateTime(
                coordinator,
                "special_price_window_end",
                "Special Price Window End",
            ),
        ]
    )


class NativeOrchestrationDateTime(OrchestrationEntity, DateTimeEntity):
    """Persist a native date/time value."""

    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator, key: str, name: str) -> None:
        OrchestrationEntity.__init__(
            self,
            coordinator,
            "datetime",
            key,
            name,
            object_id=f"load_optimizer_{key}",
        )
        self._key = key

    @property
    def native_value(self) -> datetime | None:
        return self.orchestrator._parse_datetime(self.orchestrator.state.get(self._key))

    async def async_set_value(self, value: datetime) -> None:
        await self.orchestrator.async_set(self._key, value.isoformat())
