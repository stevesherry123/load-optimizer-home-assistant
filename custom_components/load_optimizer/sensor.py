"""Sensors for Load Optimizer."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_LOAD_TYPE, DOMAIN, LOAD_TYPE_LEARNED_APPLIANCE, MANUFACTURER
from .coordinator import LoadOptimizerCoordinator
from .entity import LoadOptimizerEntity
from .orchestration_entity import OrchestrationEntity

PENCE = "p"
LEGACY_INSTANCE_ENTITY = re.compile(r"^sensor\.load_optimizer_([^_]+)_")
LEGACY_RESERVED_ATTRIBUTES = {
    "device_class",
    "friendly_name",
    "icon",
    "state_class",
    "unit_of_measurement",
}

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

NATIVE_STATUS_SENSORS = (
    (
        "overnight_readiness",
        "load_optimizer_1_overnight_readiness",
        "Overnight Readiness",
        "mdi:traffic-light",
    ),
    (
        "remote_activation",
        "load_optimizer_1_remote_activation_check",
        "Remote Activation Check",
        "mdi:remote",
    ),
    (
        "data_freshness",
        "load_optimizer_1_data_freshness",
        "Data Freshness",
        "mdi:database-clock",
    ),
    (
        "automatic_plan_resilience",
        "load_optimizer_1_automatic_plan_resilience",
        "Automatic Plan Resilience",
        "mdi:shield-sync-outline",
    ),
    (
        "negative_price_readiness",
        "load_optimizer_1_negative_price_readiness",
        "Free or Negative Price Readiness",
        "mdi:traffic-light",
    ),
)
NATIVE_STATUS_ENTITY_IDS = {
    f"sensor.{object_id}" for _, object_id, _, _ in NATIVE_STATUS_SENSORS
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Load Optimizer sensors."""
    coordinator: LoadOptimizerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        LoadOptimizerIntelligenceSensor(coordinator, key, name, unit)
        for key, name, unit in (
            ("status", "Analysis Status", None),
            ("tomorrow_classification", "Tomorrow Classification", None),
            ("tomorrow_average", "Tomorrow Average Price", "p/kWh"),
            ("volatility", "Volatility", None),
            ("pattern", "Price Pattern", None),
            ("evening_peak", "Evening Peak", None),
            ("data_quality", "Data Quality", None),
            ("summary", "Daily Summary", None),
            *((f"window_{hours}", f"Cheapest {hours} Hour Start", None) for hours in range(1, 5)),
        )
    ])
    if entry.data.get(CONF_LOAD_TYPE) == LOAD_TYPE_LEARNED_APPLIANCE:
        entities = [
            LoadOptimizerRuntimeSensor(coordinator),
            LoadOptimizerPriceCapSensor(coordinator),
            LoadOptimizerOrchestrationMigrationSensor(coordinator),
            LoadOptimizerOrchestrationStatusSensor(coordinator),
        ]
        entities.extend(
            LoadOptimizerNativeStatusSensor(coordinator, key, object_id, name, icon)
            for key, object_id, name, icon in NATIVE_STATUS_SENSORS
        )
        entities.extend(
            LoadOptimizerLegacySensor(coordinator, entity_id)
            for entity_id in sorted(coordinator.data.get("legacy_entities", {}))
            if entity_id.startswith("sensor.")
            and entity_id not in NATIVE_STATUS_ENTITY_IDS
        )
        async_add_entities(entities)
        return
    async_add_entities(
        [LoadOptimizerSensor(coordinator, description) for description in SENSOR_DESCRIPTIONS]
        + [LoadOptimizerPriceCapSensor(coordinator)]
    )


class LoadOptimizerIntelligenceSensor(LoadOptimizerEntity, SensorEntity):
    """Compact tariff analysis on its own device, without exposing history."""

    _attr_icon = "mdi:chart-bell-curve"

    def __init__(self, coordinator, key, name, unit):
        super().__init__(coordinator, f"tariff_intelligence_{key}", name)
        self.key = key
        self._attr_native_unit_of_measurement = unit
        if key.startswith("window_"):
            self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def device_info(self):
        entry = self.coordinator.config_entry
        hub = dr.async_get(self.coordinator.hass).async_get_device_by_identifier(
            (DOMAIN, entry.entry_id), entry.entry_id
        )
        return DeviceInfo(identifiers={(DOMAIN, f"{entry.entry_id}_tariff_intelligence")},
                          manufacturer=MANUFACTURER, name=f"{entry.title} Tariff Intelligence",
                          model="Deterministic tariff analysis",
                          **({"via_device_id": hub.id} if hub else {}))

    @property
    def native_value(self):
        result = self.coordinator.data.get("tariff_intelligence", {})
        if self.key.startswith("window_"):
            value = result.get("windows", {}).get(self.key[-1])
            return datetime.fromisoformat(value["start"]) if value else None
        if self.key == "tomorrow_average":
            return result.get("tomorrow_statistics", {}).get("mean")
        return result.get(self.key)

    @property
    def extra_state_attributes(self):
        result = self.coordinator.data.get("tariff_intelligence", {})
        if self.key.startswith("window_"):
            return result.get("windows", {}).get(self.key[-1])
        if self.key == "status":
            return {key: value for key, value in result.items() if key not in {"summary", "windows"}}
        return None


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
        return {
            key: value
            for key, value in self.coordinator.data.items()
            if key not in {"legacy_entities", "legacy_instances"}
        }


class LoadOptimizerPriceCapSensor(LoadOptimizerEntity, SensorEntity):
    """Expose the effective Ofgem default-tariff electricity benchmark."""

    _attr_icon = "mdi:chart-line-variant"
    _attr_native_unit_of_measurement = "p/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: LoadOptimizerCoordinator) -> None:
        super().__init__(coordinator, "ofgem_price_cap", "Ofgem Price Cap Benchmark")

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.get("price_cap", {}).get(
            "status"
        ) in {"ready", "stale"}

    @property
    def native_value(self):
        return self.coordinator.data.get("price_cap", {}).get("unit_rate_p_per_kwh")

    @property
    def extra_state_attributes(self):
        return {
            key: value
            for key, value in self.coordinator.data.get("price_cap", {}).items()
            if key != "unit_rate_p_per_kwh"
        }


class LoadOptimizerOrchestrationMigrationSensor(LoadOptimizerEntity, SensorEntity):
    """Report readiness for retiring the legacy dishwasher package."""

    _attr_icon = "mdi:swap-horizontal-bold"

    def __init__(self, coordinator: LoadOptimizerCoordinator) -> None:
        super().__init__(
            coordinator,
            "orchestration_migration",
            "Orchestration Migration",
        )

    @property
    def native_value(self):
        return self.coordinator.data.get("orchestration_migration", {}).get(
            "status",
            "not_prepared",
        )

    @property
    def extra_state_attributes(self):
        attributes = dict(self.coordinator.data.get("orchestration_migration", {}))
        orchestration = self.coordinator.data.get("orchestration", {})
        active = orchestration.get("active") is True
        legacy_enabled = orchestration.get("legacy_automations_enabled", [])
        attributes["safe_to_remove_package"] = active and not legacy_enabled
        if attributes["safe_to_remove_package"]:
            attributes["message"] = (
                "Native orchestration owns execution and all package automations "
                "are disabled. The package can be retained only as a rollback copy."
            )
        return attributes


class LoadOptimizerOrchestrationStatusSensor(OrchestrationEntity, SensorEntity):
    """Expose native orchestration ownership and queue state."""

    _attr_icon = "mdi:state-machine"

    def __init__(self, coordinator: LoadOptimizerCoordinator) -> None:
        OrchestrationEntity.__init__(
            self,
            coordinator,
            "sensor",
            "orchestration_status",
            "Orchestration Status",
        )

    @property
    def native_value(self):
        data = self.coordinator.data.get("orchestration", {})
        return data.get("execution_status", "inactive") if data.get("active") else "shadow"

    @property
    def extra_state_attributes(self):
        return self.coordinator.data.get("orchestration", {})


class LoadOptimizerNativeStatusSensor(OrchestrationEntity, SensorEntity):
    """Native replacement for a package template sensor."""

    def __init__(self, coordinator, key: str, object_id: str, name: str, icon: str) -> None:
        OrchestrationEntity.__init__(
            self,
            coordinator,
            "sensor",
            key,
            name,
            object_id=object_id,
        )
        self._key = key
        self._attr_icon = icon

    @property
    def native_value(self):
        return self.coordinator.data.get("orchestration", {}).get(self._key, {}).get(
            "state", "unknown"
        )

    @property
    def extra_state_attributes(self):
        return {
            key: value
            for key, value in self.coordinator.data.get("orchestration", {})
            .get(self._key, {})
            .items()
            if key != "state"
        }


class LoadOptimizerLegacySensor(CoordinatorEntity[LoadOptimizerCoordinator], SensorEntity):
    """Native representation of one learned-appliance runtime sensor."""

    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(self, coordinator: LoadOptimizerCoordinator, entity_id: str) -> None:
        super().__init__(coordinator)
        self.entity_id = entity_id
        self._legacy_entity_id = entity_id
        candidate_instance_id = self._instance_id_from_entity_id(entity_id)
        legacy_instances = coordinator.data.get("legacy_instances", {})
        self._instance_id = (
            candidate_instance_id
            if candidate_instance_id in legacy_instances
            else None
        )
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_legacy_"
            f"{entity_id.replace('.', '_')}"
        )
        self._apply_metadata()

    @staticmethod
    def _instance_id_from_entity_id(entity_id: str) -> str | None:
        match = LEGACY_INSTANCE_ENTITY.match(entity_id)
        return match.group(1) if match else None

    def _payload(self) -> dict[str, Any]:
        return self.coordinator.data.get("legacy_entities", {}).get(
            self._legacy_entity_id,
            {"state": "unavailable", "attributes": {}},
        )

    def _apply_metadata(self) -> None:
        attributes = self._payload().get("attributes", {})
        self._attr_name = attributes.get("friendly_name") or self._legacy_entity_id
        self._attr_icon = attributes.get("icon")
        self._attr_native_unit_of_measurement = attributes.get("unit_of_measurement")
        device_class = attributes.get("device_class")
        try:
            self._attr_device_class = SensorDeviceClass(device_class) if device_class else None
        except ValueError:
            self._attr_device_class = None
        state_class = attributes.get("state_class")
        try:
            self._attr_state_class = SensorStateClass(state_class) if state_class else None
        except ValueError:
            self._attr_state_class = None

    @property
    def available(self) -> bool:
        return super().available and self._payload().get("state") != "unavailable"

    @property
    def native_value(self):
        value = self._payload().get("state")
        if value in (None, "unknown", "unavailable"):
            return None
        if self.device_class == SensorDeviceClass.TIMESTAMP and isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return value

    @property
    def extra_state_attributes(self):
        return {
            key: value
            for key, value in self._payload().get("attributes", {}).items()
            if key not in LEGACY_RESERVED_ATTRIBUTES
        }

    @property
    def device_info(self) -> DeviceInfo:
        entry = self.coordinator.config_entry
        if self._instance_id is None:
            return DeviceInfo(
                identifiers={(DOMAIN, entry.entry_id)},
                manufacturer=MANUFACTURER,
                name=entry.title,
                model="Learned appliance optimizer",
            )
        metadata = self.coordinator.data.get("legacy_instances", {}).get(self._instance_id, {})
        hub = dr.async_get(self.coordinator.hass).async_get_device_by_identifier(
            (DOMAIN, entry.entry_id), entry.entry_id
        )
        return DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_instance_{self._instance_id}")},
            manufacturer=MANUFACTURER,
            name=metadata.get("name") or f"Load Optimizer {self._instance_id}",
            model="Learned appliance optimizer",
            **({"via_device_id": hub.id} if hub else {}),
        )
