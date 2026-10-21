"""Explicit, append-only EV views for existing storage-mode dashboards."""

import asyncio
from copy import deepcopy
from pathlib import Path

import yaml
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er


def dashboard_choices(hass):
    choices = [{"value": "", "label": "Do not add a dashboard view"}]
    data = hass.data.get(LOVELACE_DATA)
    for path, dashboard in (data.dashboards.items() if data else []):
        if isinstance(path, str) and dashboard.mode == "storage":
            choices.append({"value": path, "label": str((dashboard.config or {}).get("title", path))})
    return choices


async def async_add_ev_view(hass, entry, path):
    """Never overwrite a dashboard, an existing view, or a user's edits."""
    lock = hass.data.setdefault("load_optimizer_ev_dashboard_lock", asyncio.Lock())
    async with lock:
        data = hass.data.get(LOVELACE_DATA)
        dashboard = data.dashboards.get(path) if data else None
        if not dashboard or dashboard.mode != "storage":
            return "dashboard_unavailable"
        registry = er.async_get(hass)
        review = registry.async_get_entity_id("sensor", "load_optimizer", entry.entry_id + "_ev_charging_review")
        if not review:
            return "review_entity_unavailable"
        try:
            config = deepcopy(await dashboard.async_load(False))
            if not isinstance(config, dict) or not isinstance(config.get("views"), list):
                return "dashboard_format_unsupported"
            if any(not isinstance(view, dict) for view in config["views"]):
                return "dashboard_format_unsupported"
            view_path = "ev-" + entry.entry_id.lower()
            if any(view.get("path") == view_path for view in config["views"]):
                return "existing_view_preserved"
            original = deepcopy(config)
            def load():
                raw = Path(__file__).with_name("ev_dashboard.yaml").read_text()
                return yaml.safe_load(raw.replace("sensor.ev_charging_review", review))
            template = await hass.async_add_executor_job(load)
            cards = [card for card in template["views"][0]["cards"] if card.get("type") == "markdown"]
            config["views"].append({"title": entry.title + " Charging", "path": view_path,
                                    "icon": "mdi:ev-station", "cards": cards})
            if await dashboard.async_load(False) != original:
                return "dashboard_changed_retry"
            await dashboard.async_save(config)
            return "view_added"
        except (HomeAssistantError, OSError, ValueError, yaml.YAMLError):
            return "dashboard_update_failed"
