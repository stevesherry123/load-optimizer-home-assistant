"""Binary sensors for Load Optimizer."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import LoadOptimizerCoordinator
from .entity import LoadOptimizerEntity

BINARY_SENSOR_DESCRIPTIONS = (
    BinarySensorEntityDescription(
        key="charge_now",
        translation_key="charge_now",
        icon="mdi:ev-station",
    ),
    BinarySensorEntityDescription(
        key="ready_to_charge",
        translation_key="ready_to_charge",
        icon="mdi:check-circle-outline",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Load Optimizer binary sensors."""
    coordinator: LoadOptimizerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([LoadOptimizerBinarySensor(coordinator, description) for description in BINARY_SENSOR_DESCRIPTIONS])


class LoadOptimizerBinarySensor(LoadOptimizerEntity, BinarySensorEntity):
    """Load Optimizer binary sensor."""

    entity_description: BinarySensorEntityDescription

    def __init__(self, coordinator: LoadOptimizerCoordinator, description: BinarySensorEntityDescription) -> None:
        super().__init__(coordinator, description.key, description.name or description.key.replace("_", " ").title())
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return whether the binary sensor is on."""
        plan = self.coordinator.data.get("plan", {})
        return bool(plan.get(self.entity_description.key))

    @property
    def extra_state_attributes(self):
        """Expose selected slots on charge-now for automation debugging."""
        if self.entity_description.key != "charge_now":
            return None
        plan = self.coordinator.data.get("plan", {})
        return {
            "next_slot_start": plan.get("next_slot_start"),
            "next_slot_end": plan.get("next_slot_end"),
            "selected_slots": plan.get("selected_slots", []),
            "reason": plan.get("reason"),
        }
