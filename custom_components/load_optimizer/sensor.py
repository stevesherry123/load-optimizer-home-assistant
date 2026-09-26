"""Sensors for Load Optimizer."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_LOAD_TYPE, DOMAIN, LOAD_TYPE_LEARNED_APPLIANCE
from .coordinator import LoadOptimizerCoordinator
from .entity import LoadOptimizerEntity

PENCE = "p"

SENSOR_DESCRIPTIONS = (
    SensorEntityDescription(
        key="status",
        translation_key="status",
        icon="mdi:list-status",
    ),
    SensorEntityDescription(
        key="estimated_cost_pence",
        translation_key="estimated_cost",
        native_unit_of_measurement=PENCE,
        icon="mdi:cash-clock",
    ),
    SensorEntityDescription(
        key="estimated_profit_pence",
        translation_key="estimated_profit",
        native_unit_of_measurement=PENCE,
        icon="mdi:cash-plus",
    ),
    SensorEntityDescription(
        key="needed_battery_kwh",
        translation_key="needed_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        icon="mdi:battery-plus",
    ),
    SensorEntityDescription(
        key="wall_energy_kwh",
        translation_key="wall_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        icon="mdi:transmission-tower-import",
    ),
    SensorEntityDescription(
        key="next_slot_start",
        translation_key="next_slot_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-start",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Load Optimizer sensors."""
    coordinator: LoadOptimizerCoordinator = hass.data[DOMAIN][entry.entry_id]
    if entry.data.get(CONF_LOAD_TYPE) == LOAD_TYPE_LEARNED_APPLIANCE:
        async_add_entities([LoadOptimizerRuntimeSensor(coordinator)])
        return
    async_add_entities([LoadOptimizerSensor(coordinator, description) for description in SENSOR_DESCRIPTIONS])


class LoadOptimizerSensor(LoadOptimizerEntity, SensorEntity):
    """Load Optimizer sensor."""

    entity_description: SensorEntityDescription

    def __init__(self, coordinator: LoadOptimizerCoordinator, description: SensorEntityDescription) -> None:
        super().__init__(coordinator, description.key, description.name or description.key.replace("_", " ").title())
        self.entity_description = description

    @property
    def native_value(self):
        """Return the sensor value."""
        plan = self.coordinator.data.get("plan", {})
        value = plan.get(self.entity_description.key)
        if self.entity_description.device_class == SensorDeviceClass.TIMESTAMP and isinstance(value, str):
            return datetime.fromisoformat(value)
        return value

    @property
    def extra_state_attributes(self):
        """Expose compact planning detail on the status sensor."""
        if self.entity_description.key != "status":
            return None
        return self.coordinator.data


class LoadOptimizerRuntimeSensor(LoadOptimizerEntity, SensorEntity):
    """Status sensor for the learned-appliance compatibility runtime."""

    _attr_icon = "mdi:progress-wrench"

    def __init__(self, coordinator: LoadOptimizerCoordinator) -> None:
        super().__init__(coordinator, "runtime_status", "Runtime Status")

    @property
    def native_value(self):
        return self.coordinator.data.get("status")

    @property
    def extra_state_attributes(self):
        return self.coordinator.data
