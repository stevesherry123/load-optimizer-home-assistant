"""Config flow for Load Optimizer."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector

from .const import (
    CONF_BATTERY_CAPACITY_ENTITY,
    CONF_BATTERY_ENTITY,
    CONF_CHARGE_POWER_KW,
    CONF_CHARGER_EFFICIENCY,
    CONF_BLOCKED_WINDOW_ENTITY,
    CONF_COST_CANDIDATE_INTERVAL,
    CONF_COST_FORECAST_HOURS,
    CONF_COST_FORECAST_INTERVAL,
    CONF_COST_SEARCH_HOURS,
    CONF_GREEN_WINDOW_ENTITY,
    CONF_INSTANCES_YAML,
    CONF_CONNECTION_STATUS_ENTITY,
    CONF_LOAD_TYPE,
    CONF_PUBLISH_COST_FORECAST,
    CONF_PUBLISH_DIAGNOSTICS,
    CONF_PUBLISH_PROFILE_DATA,
    CONF_READY_BY,
    CONF_SCAN_INTERVAL,
    CONF_SCHEDULE_PREFERENCE_WEIGHT_PENCE,
    CONF_SLOT_MINUTES,
    CONF_TARGET_PERCENT,
    CONF_TARGET_PERCENT_ENTITY,
    CONF_TARIFF_ENTITIES,
    CONF_TARIFF_ENTITY,
    CONF_TARIFF_PRICE_UNIT,
    CONF_TARIFF_TIMEZONE,
    DEFAULT_CHARGER_EFFICIENCY,
    DEFAULT_LEGACY_SCAN_INTERVAL_SECONDS,
    DEFAULT_NAME,
    DEFAULT_SLOT_MINUTES,
    DEFAULT_TARGET_PERCENT,
    DEFAULT_TARIFF_PRICE_UNIT,
    DEFAULT_TARIFF_TIMEZONE,
    DOMAIN,
    LOAD_TYPE_LEARNED_APPLIANCE,
    LOAD_TYPE_EV,
    PRICE_UNITS,
)


class LoadOptimizerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Load Optimizer config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Choose a Load Optimizer setup path."""
        if user_input is not None:
            self._name = user_input[CONF_NAME]
            if user_input[CONF_LOAD_TYPE] == LOAD_TYPE_LEARNED_APPLIANCE:
                return await self.async_step_learned_appliance()
            return await self.async_step_ev()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                    vol.Required(CONF_LOAD_TYPE, default=LOAD_TYPE_LEARNED_APPLIANCE): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[LOAD_TYPE_LEARNED_APPLIANCE, LOAD_TYPE_EV],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )

    async def async_step_ev(self, user_input: dict[str, Any] | None = None):
        """Create a new EV optimizer load."""
        if user_input is not None:
            user_input[CONF_NAME] = self._name
            user_input[CONF_LOAD_TYPE] = LOAD_TYPE_EV
            await self.async_set_unique_id(f"{LOAD_TYPE_EV}_{str(self._name).lower()}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=self._name, data=user_input)

        return self.async_show_form(
            step_id="ev",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TARIFF_ENTITY): selector.EntitySelector(selector.EntitySelectorConfig()),
                    vol.Optional(CONF_TARIFF_TIMEZONE, default=DEFAULT_TARIFF_TIMEZONE): str,
                    vol.Optional(CONF_TARIFF_PRICE_UNIT, default=DEFAULT_TARIFF_PRICE_UNIT): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=PRICE_UNITS, mode=selector.SelectSelectorMode.DROPDOWN)
                    ),
                    vol.Required(CONF_BATTERY_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor")
                    ),
                    vol.Required(CONF_BATTERY_CAPACITY_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor")
                    ),
                    vol.Optional(CONF_TARGET_PERCENT_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor")
                    ),
                    vol.Optional(CONF_CONNECTION_STATUS_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor")
                    ),
                    vol.Required(CONF_CHARGE_POWER_KW): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=50)),
                    vol.Optional(CONF_TARGET_PERCENT, default=DEFAULT_TARGET_PERCENT): vol.All(
                        vol.Coerce(float), vol.Range(min=1, max=100)
                    ),
                    vol.Optional(CONF_CHARGER_EFFICIENCY, default=DEFAULT_CHARGER_EFFICIENCY): vol.All(
                        vol.Coerce(float), vol.Range(min=0.1, max=1)
                    ),
                    vol.Optional(CONF_SLOT_MINUTES, default=DEFAULT_SLOT_MINUTES): vol.All(
                        vol.Coerce(int), vol.Range(min=5, max=120)
                    ),
                    vol.Optional(CONF_READY_BY): str,
                }
            ),
        )

    async def async_step_learned_appliance(self, user_input: dict[str, Any] | None = None):
        """Create the legacy learned-appliance compatibility runtime."""
        if user_input is not None:
            user_input[CONF_NAME] = self._name
            user_input[CONF_LOAD_TYPE] = LOAD_TYPE_LEARNED_APPLIANCE
            await self.async_set_unique_id(f"{LOAD_TYPE_LEARNED_APPLIANCE}_{str(self._name).lower()}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=self._name, data=user_input)

        return self.async_show_form(
            step_id="learned_appliance",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_INSTANCES_YAML): str,
                    vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_LEGACY_SCAN_INTERVAL_SECONDS): vol.All(
                        vol.Coerce(int), vol.Range(min=10, max=3600)
                    ),
                    vol.Optional(CONF_TARIFF_ENTITY): selector.EntitySelector(selector.EntitySelectorConfig()),
                    vol.Optional(CONF_TARIFF_ENTITIES): str,
                    vol.Optional(CONF_TARIFF_TIMEZONE, default=DEFAULT_TARIFF_TIMEZONE): str,
                    vol.Optional(CONF_TARIFF_PRICE_UNIT, default=DEFAULT_TARIFF_PRICE_UNIT): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=PRICE_UNITS, mode=selector.SelectSelectorMode.DROPDOWN)
                    ),
                    vol.Optional(CONF_GREEN_WINDOW_ENTITY): str,
                    vol.Optional(CONF_BLOCKED_WINDOW_ENTITY): str,
                    vol.Optional(CONF_COST_SEARCH_HOURS, default=24): vol.All(vol.Coerce(int), vol.Range(min=1, max=72)),
                    vol.Optional(CONF_COST_FORECAST_HOURS, default=12): vol.All(vol.Coerce(int), vol.Range(min=1, max=72)),
                    vol.Optional(CONF_COST_FORECAST_INTERVAL, default=30): vol.All(
                        vol.Coerce(int), vol.Range(min=5, max=60)
                    ),
                    vol.Optional(CONF_COST_CANDIDATE_INTERVAL, default=5): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=30)
                    ),
                    vol.Optional(CONF_SCHEDULE_PREFERENCE_WEIGHT_PENCE, default=0.1): vol.All(
                        vol.Coerce(float), vol.Range(min=0, max=10)
                    ),
                    vol.Optional(CONF_PUBLISH_DIAGNOSTICS, default=False): bool,
                    vol.Optional(CONF_PUBLISH_PROFILE_DATA, default=True): bool,
                    vol.Optional(CONF_PUBLISH_COST_FORECAST, default=True): bool,
                }
            ),
        )
