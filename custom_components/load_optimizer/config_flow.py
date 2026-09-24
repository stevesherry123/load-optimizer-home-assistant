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
    CONF_CONNECTION_STATUS_ENTITY,
    CONF_LOAD_TYPE,
    CONF_READY_BY,
    CONF_SLOT_MINUTES,
    CONF_TARGET_PERCENT,
    CONF_TARGET_PERCENT_ENTITY,
    CONF_TARIFF_ENTITY,
    CONF_TARIFF_PRICE_UNIT,
    CONF_TARIFF_TIMEZONE,
    DEFAULT_CHARGER_EFFICIENCY,
    DEFAULT_NAME,
    DEFAULT_SLOT_MINUTES,
    DEFAULT_TARGET_PERCENT,
    DEFAULT_TARIFF_PRICE_UNIT,
    DEFAULT_TARIFF_TIMEZONE,
    DOMAIN,
    LOAD_TYPE_EV,
    PRICE_UNITS,
)


class LoadOptimizerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Load Optimizer config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Create a new optimizer load."""
        if user_input is not None:
            await self.async_set_unique_id(str(user_input[CONF_NAME]).lower())
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                    vol.Required(CONF_LOAD_TYPE, default=LOAD_TYPE_EV): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=[LOAD_TYPE_EV], mode=selector.SelectSelectorMode.DROPDOWN)
                    ),
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
