"""Shared native orchestration entity."""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import LoadOptimizerCoordinator


class OrchestrationEntity(CoordinatorEntity[LoadOptimizerCoordinator]):
    """Base entity attached to the first learned appliance."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: LoadOptimizerCoordinator,
        domain: str,
        key: str,
        name: str,
        *,
        object_id: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.entity_id = f"{domain}.{object_id or f'load_optimizer_1_{key}'}"
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_orchestration_{key}"
        )
        self._attr_name = name

    @property
    def orchestrator(self):
        return self.coordinator.orchestrator

    @property
    def device_info(self) -> DeviceInfo:
        entry = self.coordinator.config_entry
        hub = dr.async_get(self.coordinator.hass).async_get_device_by_identifier(
            (DOMAIN, entry.entry_id), entry.entry_id
        )
        return DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_instance_1")},
            manufacturer=MANUFACTURER,
            name="Dishwasher 1",
            model="Learned appliance optimizer",
            **({"via_device_id": hub.id} if hub else {}),
        )
