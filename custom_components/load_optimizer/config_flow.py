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
    CONF_BOSCH_CONNECTED_SENSOR,
    CONF_BOSCH_DEVICE_ID,
    CONF_BOSCH_DOOR_SENSOR,
    CONF_BOSCH_OPERATION_STATE_SENSOR,
    CONF_BOSCH_POWER_STATE_SENSOR,
    CONF_BOSCH_POWER_SWITCH,
    CONF_BOSCH_PROGRAM_SELECT,
    CONF_BOSCH_REMOTE_CONTROL_SENSOR,
    CONF_BOSCH_REMOTE_START_SENSOR,
    CONF_BOSCH_SELECTED_PROGRAM_SENSOR,
    CONF_BOSCH_START_BUTTON,
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
    CONF_PRICE_CAP_PAYMENT_METHOD,
    CONF_PRICE_CAP_REGION,
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
    DEFAULT_PRICE_CAP_REGION,
    DEFAULT_PRICE_CAP_PAYMENT_METHOD,
    DEFAULT_SLOT_MINUTES,
    DEFAULT_TARGET_PERCENT,
    DEFAULT_TARIFF_PRICE_UNIT,
    DEFAULT_TARIFF_TIMEZONE,
    DOMAIN,
    LOAD_TYPE_LEARNED_APPLIANCE,
    LOAD_TYPE_EV,
    OFGEM_REGIONS,
    PRICE_CAP_PAYMENT_METHODS,
    PRICE_UNITS,
)


def _price_cap_schema(existing: dict[str, Any] | None = None) -> dict[Any, Any]:
    """Return shared Ofgem price-cap configuration fields."""
    existing = existing or {}
    return {
        vol.Required(
            CONF_PRICE_CAP_REGION,
            default=existing.get(CONF_PRICE_CAP_REGION, DEFAULT_PRICE_CAP_REGION),
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=OFGEM_REGIONS,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(
            CONF_PRICE_CAP_PAYMENT_METHOD,
            default=existing.get(
                CONF_PRICE_CAP_PAYMENT_METHOD,
                DEFAULT_PRICE_CAP_PAYMENT_METHOD,
            ),
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=PRICE_CAP_PAYMENT_METHODS,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
    }


def _ev_schema(existing: dict[str, Any] | None = None) -> dict[Any, Any]:
    """Share setup/edit fields; optional references are suggestions, not defaults."""
    existing = existing or {}
    schema: dict[Any, Any] = {}
    for key, required, domain in (
        (CONF_TARIFF_ENTITY, True, None),
        (CONF_BATTERY_ENTITY, True, "sensor"),
        (CONF_BATTERY_CAPACITY_ENTITY, True, "sensor"),
        (CONF_TARGET_PERCENT_ENTITY, False, "sensor"),
        (CONF_CONNECTION_STATUS_ENTITY, False, "sensor"),
    ):
        value = existing.get(key)
        kwargs = {}
        if value:
            kwargs = (
                {"default": value} if required
                else {"description": {"suggested_value": value}}
            )
        marker = vol.Required if required else vol.Optional
        config = (
            selector.EntitySelectorConfig(domain=domain)
            if domain else selector.EntitySelectorConfig()
        )
        schema[marker(key, **kwargs)] = selector.EntitySelector(config)
    power_default = (
        {"default": existing[CONF_CHARGE_POWER_KW]}
        if CONF_CHARGE_POWER_KW in existing else {}
    )
    schema.update(
        {
            vol.Optional(
                CONF_TARIFF_TIMEZONE,
                default=existing.get(CONF_TARIFF_TIMEZONE, DEFAULT_TARIFF_TIMEZONE),
            ): str,
            vol.Optional(
                CONF_TARIFF_PRICE_UNIT,
                default=existing.get(CONF_TARIFF_PRICE_UNIT, DEFAULT_TARIFF_PRICE_UNIT),
            ): selector.SelectSelector(selector.SelectSelectorConfig(
                options=PRICE_UNITS, mode=selector.SelectSelectorMode.DROPDOWN,
            )),
            vol.Required(CONF_CHARGE_POWER_KW, **power_default):
                vol.All(vol.Coerce(float), vol.Range(min=0.1, max=50)),
            vol.Optional(
                CONF_TARGET_PERCENT,
                default=existing.get(CONF_TARGET_PERCENT, DEFAULT_TARGET_PERCENT),
            ): vol.All(vol.Coerce(float), vol.Range(min=1, max=100)),
            vol.Optional(
                CONF_CHARGER_EFFICIENCY,
                default=existing.get(CONF_CHARGER_EFFICIENCY, DEFAULT_CHARGER_EFFICIENCY),
            ): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=1)),
            vol.Optional(
                CONF_SLOT_MINUTES,
                default=existing.get(CONF_SLOT_MINUTES, DEFAULT_SLOT_MINUTES),
            ): vol.All(vol.Coerce(int), vol.Range(min=5, max=120)),
            vol.Optional(
                CONF_READY_BY,
                description={"suggested_value": existing[CONF_READY_BY]}
                if existing.get(CONF_READY_BY) else {},
            ): vol.Any("", vol.Match(r"^(?:[01]\d|2[0-3]):[0-5]\d$")),
        }
    )
    return schema


class LoadOptimizerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Load Optimizer config flow."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Return the options flow."""
        return LoadOptimizerOptionsFlow()

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
                    **_ev_schema(),
                    **_price_cap_schema(),
                }
            ),
        )

    async def async_step_learned_appliance(
        self, user_input: dict[str, Any] | None = None
    ):
        """Create the learned-appliance runtime."""
        if any(
            entry.data.get(CONF_LOAD_TYPE) == LOAD_TYPE_LEARNED_APPLIANCE
            for entry in self._async_current_entries()
        ):
            return self.async_abort(reason="learned_appliance_already_configured")
        if user_input is not None:
            user_input[CONF_NAME] = self._name
            user_input[CONF_LOAD_TYPE] = LOAD_TYPE_LEARNED_APPLIANCE
            await self.async_set_unique_id(LOAD_TYPE_LEARNED_APPLIANCE)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=self._name, data=user_input)

        return self.async_show_form(
            step_id="learned_appliance",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_INSTANCES_YAML): str,
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=DEFAULT_LEGACY_SCAN_INTERVAL_SECONDS,
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
                    vol.Optional(CONF_TARIFF_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig()
                    ),
                    vol.Optional(CONF_TARIFF_ENTITIES): str,
                    vol.Optional(
                        CONF_TARIFF_TIMEZONE,
                        default=DEFAULT_TARIFF_TIMEZONE,
                    ): str,
                    vol.Optional(
                        CONF_TARIFF_PRICE_UNIT,
                        default=DEFAULT_TARIFF_PRICE_UNIT,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=PRICE_UNITS,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(CONF_GREEN_WINDOW_ENTITY): str,
                    vol.Optional(CONF_BLOCKED_WINDOW_ENTITY): str,
                    vol.Optional(CONF_COST_SEARCH_HOURS, default=24): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=72)
                    ),
                    vol.Optional(CONF_COST_FORECAST_HOURS, default=12): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=72)
                    ),
                    vol.Optional(CONF_COST_FORECAST_INTERVAL, default=30): vol.All(
                        vol.Coerce(int), vol.Range(min=5, max=60)
                    ),
                    vol.Optional(CONF_COST_CANDIDATE_INTERVAL, default=5): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=30)
                    ),
                    vol.Optional(
                        CONF_SCHEDULE_PREFERENCE_WEIGHT_PENCE,
                        default=0.1,
                    ): vol.All(vol.Coerce(float), vol.Range(min=0, max=10)),
                    vol.Optional(CONF_PUBLISH_DIAGNOSTICS, default=False): bool,
                    vol.Optional(CONF_PUBLISH_PROFILE_DATA, default=True): bool,
                    vol.Optional(CONF_PUBLISH_COST_FORECAST, default=True): bool,
                    **_price_cap_schema(),
                }
            ),
        )


class LoadOptimizerOptionsFlow(config_entries.OptionsFlow):
    """Edit load settings without exposing one giant form."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Route to the options supported by this load type."""
        load_type = self.config_entry.data.get(CONF_LOAD_TYPE)
        if load_type == LOAD_TYPE_EV:
            return self.async_show_menu(step_id="init", menu_options=["ev", "price_cap"])
        if load_type != LOAD_TYPE_LEARNED_APPLIANCE:
            return self.async_abort(reason="not_supported")

        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "appliances_tariff",
                "optimisation",
                "publishing",
                "price_cap",
                "dishwasher_control",
            ],
        )

    @property
    def _existing(self) -> dict[str, Any]:
        """Return setup data with saved options taking precedence."""
        return {**self.config_entry.data, **self.config_entry.options}

    def _save_section(self, user_input: dict[str, Any]):
        """Merge one options section without discarding the other sections."""
        return self.async_create_entry(
            title="",
            data={**self.config_entry.options, **user_input},
        )

    async def async_step_ev(self, user_input: dict[str, Any] | None = None):
        """Edit EV inputs without replacing its config entry or opt-ins."""
        if user_input is not None:
            updates = dict(user_input)
            for field in (CONF_TARGET_PERCENT_ENTITY, CONF_CONNECTION_STATUS_ENTITY, CONF_READY_BY):
                updates.setdefault(field, "")
            return self._save_section(updates)
        return self.async_show_form(
            step_id="ev",
            data_schema=vol.Schema(_ev_schema(self._existing)),
        )

    async def async_step_appliances_tariff(
        self, user_input: dict[str, Any] | None = None
    ):
        """Edit appliance sources and tariff inputs."""
        if user_input is not None:
            return self._save_section(user_input)

        existing = self._existing
        return self.async_show_form(
            step_id="appliances_tariff",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_INSTANCES_YAML,
                        default=existing.get(CONF_INSTANCES_YAML, ""),
                    ): str,
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=existing.get(
                            CONF_SCAN_INTERVAL,
                            DEFAULT_LEGACY_SCAN_INTERVAL_SECONDS,
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
                    vol.Optional(
                        CONF_TARIFF_ENTITY,
                        default=existing.get(CONF_TARIFF_ENTITY, ""),
                    ): selector.EntitySelector(selector.EntitySelectorConfig()),
                    vol.Optional(
                        CONF_TARIFF_ENTITIES,
                        default=existing.get(CONF_TARIFF_ENTITIES, ""),
                    ): str,
                    vol.Optional(
                        CONF_TARIFF_TIMEZONE,
                        default=existing.get(
                            CONF_TARIFF_TIMEZONE,
                            DEFAULT_TARIFF_TIMEZONE,
                        ),
                    ): str,
                    vol.Optional(
                        CONF_TARIFF_PRICE_UNIT,
                        default=existing.get(
                            CONF_TARIFF_PRICE_UNIT,
                            DEFAULT_TARIFF_PRICE_UNIT,
                        ),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=PRICE_UNITS,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        CONF_GREEN_WINDOW_ENTITY,
                        default=existing.get(CONF_GREEN_WINDOW_ENTITY, ""),
                    ): str,
                    vol.Optional(
                        CONF_BLOCKED_WINDOW_ENTITY,
                        default=existing.get(CONF_BLOCKED_WINDOW_ENTITY, ""),
                    ): str,
                }
            ),
        )

    async def async_step_optimisation(
        self, user_input: dict[str, Any] | None = None
    ):
        """Edit cost-search and scheduling settings."""
        if user_input is not None:
            return self._save_section(user_input)

        existing = self._existing
        return self.async_show_form(
            step_id="optimisation",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_COST_SEARCH_HOURS,
                        default=existing.get(CONF_COST_SEARCH_HOURS, 24),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=72)),
                    vol.Optional(
                        CONF_COST_FORECAST_HOURS,
                        default=existing.get(CONF_COST_FORECAST_HOURS, 12),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=72)),
                    vol.Optional(
                        CONF_COST_FORECAST_INTERVAL,
                        default=existing.get(CONF_COST_FORECAST_INTERVAL, 30),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=60)),
                    vol.Optional(
                        CONF_COST_CANDIDATE_INTERVAL,
                        default=existing.get(CONF_COST_CANDIDATE_INTERVAL, 5),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=30)),
                    vol.Optional(
                        CONF_SCHEDULE_PREFERENCE_WEIGHT_PENCE,
                        default=existing.get(
                            CONF_SCHEDULE_PREFERENCE_WEIGHT_PENCE,
                            0.1,
                        ),
                    ): vol.All(vol.Coerce(float), vol.Range(min=0, max=10)),
                }
            ),
        )

    async def async_step_publishing(
        self, user_input: dict[str, Any] | None = None
    ):
        """Edit optional diagnostic and forecast publishing settings."""
        if user_input is not None:
            return self._save_section(user_input)

        existing = self._existing
        return self.async_show_form(
            step_id="publishing",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_PUBLISH_DIAGNOSTICS,
                        default=existing.get(CONF_PUBLISH_DIAGNOSTICS, False),
                    ): bool,
                    vol.Optional(
                        CONF_PUBLISH_PROFILE_DATA,
                        default=existing.get(CONF_PUBLISH_PROFILE_DATA, True),
                    ): bool,
                    vol.Optional(
                        CONF_PUBLISH_COST_FORECAST,
                        default=existing.get(CONF_PUBLISH_COST_FORECAST, True),
                    ): bool,
                }
            ),
        )

    async def async_step_dishwasher_control(
        self, user_input: dict[str, Any] | None = None
    ):
        """Edit optional Home Connect dishwasher control references."""
        if user_input is not None:
            return self._save_section(user_input)

        existing = self._existing
        schema: dict[Any, Any] = {}
        entity_fields = (
            CONF_BOSCH_POWER_SWITCH,
            CONF_BOSCH_PROGRAM_SELECT,
            CONF_BOSCH_START_BUTTON,
            CONF_BOSCH_SELECTED_PROGRAM_SENSOR,
            CONF_BOSCH_POWER_STATE_SENSOR,
            CONF_BOSCH_CONNECTED_SENSOR,
            CONF_BOSCH_DOOR_SENSOR,
            CONF_BOSCH_REMOTE_CONTROL_SENSOR,
            CONF_BOSCH_REMOTE_START_SENSOR,
            CONF_BOSCH_OPERATION_STATE_SENSOR,
        )
        schema[
            vol.Optional(
                CONF_BOSCH_DEVICE_ID,
                default=existing.get(CONF_BOSCH_DEVICE_ID, ""),
            )
        ] = str
        for field in entity_fields:
            schema[
                vol.Optional(field, default=existing.get(field, ""))
            ] = selector.EntitySelector(selector.EntitySelectorConfig())
        return self.async_show_form(
            step_id="dishwasher_control",
            data_schema=vol.Schema(schema),
        )

    async def async_step_price_cap(
        self, user_input: dict[str, Any] | None = None
    ):
        """Edit the regional Ofgem benchmark configuration."""
        if user_input is not None:
            return self._save_section(user_input)

        return self.async_show_form(
            step_id="price_cap",
            data_schema=vol.Schema(_price_cap_schema(self._existing)),
        )
