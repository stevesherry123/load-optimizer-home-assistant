"""Guided EV source selection and read-only plan review."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import voluptuous as vol
from homeassistant.helpers import selector

from .const import EV_CONTROL_ENTITY_FIELDS
from .ev_dashboard import dashboard_choices
from .optimizer.ev_setup import inspect_ev_setup, tariff_entities

SOURCE_FIELDS = {"tariff_entity", "tariff_entities", "tariff_timezone", "tariff_price_unit",
                 "battery_entity", "battery_capacity_entity", "target_percent_entity", "connection_status_entity"}


class EVGuidedFlow:
    """Stage all edits until the user explicitly saves a fresh read-only review."""

    def _guided_schema(self, sources):
        from .config_flow import _ev_schema

        existing = {**getattr(self, "_existing", {}), **getattr(self, "_ev_pending", {})}
        return vol.Schema({key: value for key, value in _ev_schema(existing).items()
                           if (key.schema in SOURCE_FIELDS) == sources})

    async def async_step_ev_setup(self, user_input=None):
        if not hasattr(self, "_ev_pending"):
            self._ev_pending = dict(getattr(self, "_existing", {}))
        if user_input is not None:
            from .config_flow import _ev_input_errors

            values = {**self._ev_pending, **user_input}
            errors = _ev_input_errors(values)
            if not errors:
                self._ev_pending.update(user_input)
                for key in ("target_percent_entity", "connection_status_entity"):
                    self._ev_pending[key] = user_input.get(key, "")
                return await self.async_step_ev_preferences()
        else:
            errors = {}
        return self.async_show_form(step_id="ev_setup", data_schema=self._guided_schema(True), errors=errors)

    async def async_step_ev_preferences(self, user_input=None):
        if not hasattr(self, "_ev_pending"):
            return await self.async_step_ev_setup()
        errors = {}
        if user_input is not None:
            from .config_flow import _ev_input_errors

            values = {**self._ev_pending, **user_input}
            errors = _ev_input_errors(values)
            if not errors:
                self._ev_pending.update(user_input)
                for key in ["ready_by", *(key for key, _ in EV_CONTROL_ENTITY_FIELDS)]:
                    self._ev_pending[key] = user_input.get(key, "")
                self._ev_pending["slot_minutes"] = int(self._ev_pending.get("slot_minutes", 30))
                return await self.async_step_ev_review()
        return self.async_show_form(step_id="ev_preferences", data_schema=self._guided_schema(False), errors=errors)

    def _guided_review(self):
        config = self._ev_pending
        ids = tariff_entities(config) + [value for key, value in config.items()
            if isinstance(value, str) and (key.endswith("_entity") or key == "ev_charger_switch") and value]
        states = {}
        for entity_id in ids:
            state = self.hass.states.get(entity_id)
            if state:
                states[entity_id] = {"state": state.state, "attributes": dict(state.attributes),
                    "last_reported": (getattr(state, "last_reported", None) or state.last_updated).isoformat()}
        return inspect_ev_setup(config, states, datetime.now(timezone.utc))

    async def async_step_ev_review(self, user_input=None):
        if not hasattr(self, "_ev_pending"):
            return await self.async_step_ev_setup()
        if "charge_power_kw" not in self._ev_pending:
            return await self.async_step_ev_preferences()
        action = (user_input or {}).get("action", "refresh")
        if action == "edit_sources":
            return await self.async_step_ev_setup()
        if action == "edit_preferences":
            return await self.async_step_ev_preferences()
        report = self._guided_review()
        errors = {}
        choices = dashboard_choices(self.hass)
        if user_input and action == "save":
            path = user_input.get("ev_dashboard_path", "")
            if path and path not in {choice["value"] for choice in choices}:
                errors["base"] = "ev_dashboard_unavailable"
            elif report["issues"] and not user_input.get("accept_incomplete", False):
                errors["base"] = "ev_review_incomplete"
            else:
                pending = {**self._ev_pending, "ev_dashboard_path": path}
                if hasattr(self, "_save_section"):
                    from .config_flow import _ev_schema

                    fields = {key.schema for key in _ev_schema()} | {"ev_dashboard_path"}
                    return self._save_section({key:value for key,value in pending.items() if key in fields})
                await self.async_set_unique_id(f"ev_charging_{str(self._name).lower()}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=self._name,
                    data={**pending, "name": self._name, "load_type": "ev_charging"})
        plan = report["plan"]
        rows = ["**Read-only preview. Saving does not enable automatic charging.**",
                "Saving an existing entry reloads it and stops any session it owns.",
                f"Plan: {plan.get('status', 'not_ready')}. Tariff intervals: {report['period_count']}.",
                f"Estimated supply energy: {plan.get('wall_energy_kwh', 'unavailable')} kWh. "
                f"Estimated cost: {plan.get('estimated_cost_pence', 'unavailable')} p.",
                f"Session limits: {self._ev_pending.get('ev_session_max_hours', 24)} hours including waiting; "
                f"{self._ev_pending.get('ev_session_max_energy_kwh', 120)} kWh."]
        rows += ["- " + issue.replace("_", " ") for issue in report["issues"]]
        rows += ["- " + warning for warning in report["warnings"]]
        if report["control_ready"]:
            rows.append("Input checks passed. Physical charging is not yet verified; activation rechecks live safety conditions.")
        elif not report["control_configured"]:
            rows.append("Advisory only: no charger switch is configured.")
        rows += ["", "| Selected time | Price |", "|---|---:|"]
        zone = ZoneInfo(self._ev_pending.get("tariff_timezone", "Europe/London"))
        slots = plan.get("selected_slots", [])
        for slot in slots[:12]:
            start = datetime.fromisoformat(slot["start"]).astimezone(zone)
            end = datetime.fromisoformat(slot["end"]).astimezone(zone)
            rows.append(f"| {start:%a %H:%M %Z} to {end:%a %H:%M %Z} | {slot['price_p_per_kwh']} p/kWh |")
        if len(slots) > 12:
            rows.append(f"Showing 12 of {len(slots)} selected intervals; the saved review sensor exposes the full plan.")
        default_path = self._ev_pending.get("ev_dashboard_path", "")
        if default_path not in {choice["value"] for choice in choices}:
            default_path = ""
        return self.async_show_form(step_id="ev_review", errors=errors,
            description_placeholders={"review": "\n".join(rows)}, data_schema=vol.Schema({
                vol.Required("action", default="save"): selector.SelectSelector(selector.SelectSelectorConfig(
                    options=[{"value": "save", "label": "Save configuration"},
                             {"value": "refresh", "label": "Refresh preview"},
                             {"value": "edit_sources", "label": "Edit data sources"},
                             {"value": "edit_preferences", "label": "Edit charging preferences"}],
                    mode=selector.SelectSelectorMode.DROPDOWN)),
                vol.Optional("accept_incomplete", default=False): bool,
                vol.Optional("ev_dashboard_path", default=default_path): selector.SelectSelector(selector.SelectSelectorConfig(
                    options=choices, mode=selector.SelectSelectorMode.DROPDOWN)),
            }))
