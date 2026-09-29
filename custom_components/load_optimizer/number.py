"""Native orchestration numeric controls."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
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
    async_add_entities([NativeSpecialPrice(coordinator)])


class NativeSpecialPrice(OrchestrationEntity, NumberEntity):
    """Special price window unit price."""

    _attr_icon = "mdi:currency-gbp"
    _attr_native_min_value = -100.0
    _attr_native_max_value = 100.0
    _attr_native_step = 0.01
    _attr_native_unit_of_measurement = "p/kWh"
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator) -> None:
        OrchestrationEntity.__init__(
            self,
            coordinator,
            "number",
            "special_price_window_price",
            "Special Price",
            object_id="load_optimizer_special_price_window_price",
        )

    @property
    def native_value(self) -> float:
        return float(self.orchestrator.state.get("special_price_window_price", 0))

    async def async_set_native_value(self, value: float) -> None:
        await self.orchestrator.async_set("special_price_window_price", value)
