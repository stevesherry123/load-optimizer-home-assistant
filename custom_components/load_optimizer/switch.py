"""Native orchestration switches."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_LOAD_TYPE, DOMAIN, LOAD_TYPE_LEARNED_APPLIANCE
from .coordinator import LoadOptimizerCoordinator
from .orchestration_entity import OrchestrationEntity
from .entity import LoadOptimizerEntity

SWITCHES = (
    ("auto_mode_enabled", "Schedule After Loading", "mdi:robot"),
    (
        "auto_negative_price_enabled",
        "Profitable Extra Runs",
        "mdi:transmission-tower-export",
    ),
    (
        "special_price_window_enabled",
        "Special Price Window Enabled",
        "mdi:calendar-star",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: LoadOptimizerCoordinator = hass.data[DOMAIN][entry.entry_id]
    if entry.data.get(CONF_LOAD_TYPE) != LOAD_TYPE_LEARNED_APPLIANCE:
        if coordinator.ev_adapter:
            async_add_entities([EVControlPermissionSwitch(coordinator)])
        return
    async_add_entities(
        NativeOrchestrationSwitch(coordinator, key, name, icon)
        for key, name, icon in SWITCHES
    )


class EVControlPermissionSwitch(LoadOptimizerEntity, SwitchEntity):
    """Explicit session permission, always off after setup or reload."""

    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator):
        super().__init__(coordinator, "ev_control_enabled", "Automatic Charging")

    @property
    def is_on(self) -> bool:
        return self.coordinator.ev_control_enabled

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_ev_control(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_ev_control(False)


class NativeOrchestrationSwitch(OrchestrationEntity, SwitchEntity):
    """Persisted native orchestration switch."""

    def __init__(self, coordinator, key: str, name: str, icon: str) -> None:
        object_id = (
            "load_optimizer_special_price_window_enabled"
            if key == "special_price_window_enabled"
            else None
        )
        OrchestrationEntity.__init__(
            self,
            coordinator,
            "switch",
            key,
            name,
            object_id=object_id,
        )
        self._key = key
        self._attr_icon = icon

    @property
    def is_on(self) -> bool:
        return bool(self.orchestrator.state.get(self._key))

    async def async_turn_on(self, **kwargs) -> None:
        await self.orchestrator.async_set(self._key, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.orchestrator.async_set(self._key, False)
