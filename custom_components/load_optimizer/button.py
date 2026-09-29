"""Native orchestration buttons."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_LOAD_TYPE, DOMAIN, LOAD_TYPE_LEARNED_APPLIANCE
from .coordinator import LoadOptimizerCoordinator
from .orchestration_entity import OrchestrationEntity

BUTTONS = (
    ("request_now", "Request Start Now", "mdi:play-circle", "now", False),
    ("request_soon", "Request Start Soon", "mdi:clock-fast", "soon", False),
    (
        "request_overnight",
        "Request Overnight",
        "mdi:weather-night",
        "overnight",
        False,
    ),
    (
        "request_now_override",
        "Request Selected Program Now",
        "mdi:play-circle-outline",
        "now",
        True,
    ),
    (
        "request_soon_override",
        "Request Selected Program Soon",
        "mdi:clock-fast",
        "soon",
        True,
    ),
    (
        "request_overnight_override",
        "Request Selected Program Overnight",
        "mdi:weather-night",
        "overnight",
        True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if entry.data.get(CONF_LOAD_TYPE) != LOAD_TYPE_LEARNED_APPLIANCE:
        return
    coordinator: LoadOptimizerCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        NativeRequestButton(coordinator, key, name, icon, mode, override)
        for key, name, icon, mode, override in BUTTONS
    ]
    entities.extend(
        [
            NativeActionButton(
                coordinator,
                "cancel_schedule",
                "Cancel Schedule",
                "mdi:cancel",
                "cancel",
            ),
            NativeActionButton(
                coordinator,
                "recalculate_now",
                "Recalculate Recommendations",
                "mdi:refresh",
                "recalculate",
            ),
        ]
    )
    async_add_entities(entities)


class NativeRequestButton(OrchestrationEntity, ButtonEntity):
    """Create a native scheduling request."""

    def __init__(self, coordinator, key, name, icon, mode, override) -> None:
        OrchestrationEntity.__init__(self, coordinator, "button", key, name)
        self._attr_icon = icon
        self._mode = mode
        self._override = override

    async def async_press(self) -> None:
        await self.orchestrator.async_request(
            self._mode,
            override=self._override,
        )


class NativeActionButton(OrchestrationEntity, ButtonEntity):
    """Run a non-request orchestration action."""

    def __init__(self, coordinator, key, name, icon, action) -> None:
        OrchestrationEntity.__init__(self, coordinator, "button", key, name)
        self._attr_icon = icon
        self._action = action

    async def async_press(self) -> None:
        if self._action == "cancel":
            await self.orchestrator.async_cancel()
        else:
            await self.orchestrator.async_recalculate()
