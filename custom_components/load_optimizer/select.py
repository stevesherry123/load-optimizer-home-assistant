"""Native orchestration selects."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
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
    async_add_entities([NativeProgramSelect(coordinator)])


class NativeProgramSelect(OrchestrationEntity, SelectEntity):
    """Select an explicit dishwasher program."""

    _attr_icon = "mdi:format-list-bulleted"

    def __init__(self, coordinator) -> None:
        OrchestrationEntity.__init__(
            self,
            coordinator,
            "select",
            "override_program",
            "Dishwasher 1 Override Program",
        )

    @property
    def options(self) -> list[str]:
        return self.orchestrator.program_options

    @property
    def current_option(self) -> str | None:
        return self.orchestrator.state.get("override_program")

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ValueError(f"Unsupported program: {option}")
        await self.orchestrator.async_set("override_program", option)
