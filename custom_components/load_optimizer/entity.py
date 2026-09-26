"""Shared entity helpers for Load Optimizer."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_LOAD_TYPE, DOMAIN, LOAD_TYPE_LEARNED_APPLIANCE, MANUFACTURER
from .coordinator import LoadOptimizerCoordinator


class LoadOptimizerEntity(CoordinatorEntity[LoadOptimizerCoordinator]):
    """Base Load Optimizer entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LoadOptimizerCoordinator, suffix: str, name: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{suffix}"
        self._attr_translation_key = suffix
        self._attr_name = name

    @property
    def device_info(self) -> DeviceInfo:
        entry = self.coordinator.config_entry
        model = (
            "Learned appliance optimizer"
            if entry.data.get(CONF_LOAD_TYPE) == LOAD_TYPE_LEARNED_APPLIANCE
            else "EV charging optimizer"
        )
        return DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer=MANUFACTURER,
            name=entry.title,
            model=model,
        )
