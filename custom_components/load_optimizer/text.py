"""Native orchestration text controls."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_LOAD_TYPE, DOMAIN, LOAD_TYPE_LEARNED_APPLIANCE
from .coordinator import LoadOptimizerCoordinator
from .orchestration_entity import OrchestrationEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    if entry.data.get(CONF_LOAD_TYPE) != LOAD_TYPE_LEARNED_APPLIANCE:
        return
    coordinator: LoadOptimizerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NativeSpecialPriceLabel(coordinator)])


class NativeSpecialPriceLabel(OrchestrationEntity, TextEntity):
    """Special price window display label."""

    _attr_icon = "mdi:label-outline"
    _attr_native_min = 0
    _attr_native_max = 64

    def __init__(self, coordinator) -> None:
        OrchestrationEntity.__init__(
            self,
            coordinator,
            "text",
            "special_price_window_label",
            "Special Price Window Label",
            object_id="load_optimizer_special_price_window_label",
        )

    @property
    def native_value(self) -> str:
        return str(self.orchestrator.state.get("special_price_window_label", ""))

    async def async_set_value(self, value: str) -> None:
        await self.orchestrator.async_set("special_price_window_label", value)
