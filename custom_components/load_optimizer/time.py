"""Configurable local overnight window for normal dishwasher requests."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_LOAD_TYPE, DOMAIN, LOAD_TYPE_LEARNED_APPLIANCE
from .orchestration_entity import OrchestrationEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    if entry.data.get(CONF_LOAD_TYPE) != LOAD_TYPE_LEARNED_APPLIANCE:
        return
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        NativeOvernightTime(coordinator, "start", "Overnight Start"),
        NativeOvernightTime(coordinator, "end", "Dishes Ready By"),
    ])


class NativeOvernightTime(OrchestrationEntity, TimeEntity):
    """Persist the default for subsequent requests without moving queued windows."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator, key: str, name: str) -> None:
        OrchestrationEntity.__init__(self, coordinator, "time", f"overnight_{key}", name)
        self._key = key

    @property
    def native_value(self) -> time:
        return time.fromisoformat(self.orchestrator.overnight_time(self._key))

    async def async_set_value(self, value: time) -> None:
        await self.orchestrator.async_set(f"overnight_{self._key}", value.strftime("%H:%M"))
