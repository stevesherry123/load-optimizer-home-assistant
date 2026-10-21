"""Exercise dashboard templates with the real minimum Home Assistant runtime."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

import yaml
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util


ROOT = Path(__file__).resolve().parents[1]
PRICE_ENTITY = "sensor.load_optimizer_1_current_energy_price"
BENCHMARK_ENTITY = "sensor.load_optimizer_ofgem_price_cap_benchmark"
CASES = (
    ("20", "27.86", "#d9f2df"),
    ("27.86", "27.86", "#fff3cd"),
    ("35", "27.86", "#ef5350"),
    ("-5", "27.86", "#d9f2df"),
    ("0", "0", "#fff3cd"),
    ("27.8601", "27.86", "#fff3cd"),
    ("27.8599", "27.86", "#fff3cd"),
    ("unknown", "27.86", "var(--ha-card-background"),
    ("unavailable", "27.86", "var(--ha-card-background"),
    ("20", "unavailable", "var(--ha-card-background"),
    ("20", "unknown", "var(--ha-card-background"),
    ("nan", "27.86", "var(--ha-card-background"),
    ("20", "inf", "var(--ha-card-background"),
)


def cards(value):
    if isinstance(value, dict):
        if "type" in value:
            yield value
        for child in value.values():
            yield from cards(child)
    elif isinstance(value, list):
        for child in value:
            yield from cards(child)


async def main():
    styles = []
    scheduling_templates = []
    dt_util.set_default_time_zone(ZoneInfo("Europe/London"))
    with TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        for path in (
            "custom_components/load_optimizer/dashboard.yaml",
            "homeassistant/dashboards/full/load_optimizer_dashboard.yaml",
        ):
            dashboard = yaml.safe_load((ROOT / path).read_text())
            tiles = list(cards(dashboard))
            current = next(card for card in tiles if card.get("entity") == PRICE_ENTITY)
            reference = next(card for card in tiles if card.get("entity") == BENCHMARK_ENTITY)
            assert "card_mod" not in reference, "Benchmark tile must remain neutral"
            style = current["card_mod"]["style"]
            styles.append(style)
            template = Template(style, hass)
            for price, benchmark, expected in CASES:
                hass.states.async_set(PRICE_ENTITY, price)
                hass.states.async_set(BENCHMARK_ENTITY, benchmark)
                rendered = template.async_render({"config": current}, parse_result=False)
                assert "background: " + expected in rendered, (path, price, benchmark, rendered)
            print(f"{path}: {len(CASES)} colour/fallback cases passed")
            content = next(card["content"] for card in tiles if card.get("title") == "Automatic Scheduling")
            scheduling_templates.append(content)
            template = Template(content, hass)
            explanation = "sensor.load_optimizer_1_automation_explanation"
            orchestration = "sensor.load_optimizer_1_orchestration_status"
            cost = "sensor.load_optimizer_1_cost_status"
            hass.states.async_set(explanation, "waiting", {
                "summary": "Waiting for prices through the whole overnight window.",
                "blockers": ["power_source_unavailable", "blocked_window_source_unavailable"],
                "warnings": ["negative_price_retry_cooldown"],
            })
            hass.states.async_set(cost, "ready", {
                "free_window_source_ready": False,
                "decision_policy": {"cooldown_programs": [
                    {"program": "MixedLoad", "cooldown_until": "2026-10-20T13:54:00+00:00"},
                    {"program": "Quick45", "cooldown_until": "invalid"},
                ]},
            })
            rendered = template.async_render(parse_result=False)
            for expected in ("automatic starts are paused", "30-minute automatic request interval",
                             "Free-electricity pricing unavailable", "MixedLoad", "Tue 20 Oct 14:54 BST",
                             "These cooldowns apply to automatic runs only", "None recorded"):
                assert expected in rendered, (path, expected, rendered)
            assert "power_source_unavailable" not in rendered
            assert "blocked_window_source_unavailable" not in rendered
            hass.states.async_set(explanation, "appliance_scheduled", {
                "summary": "The dishwasher's own delayed-start timer is set. It is waiting, not washing.",
                "action_required": "Use the dishwasher controls to change its timer.",
                "blockers": ["appliance_delayed_start_pending"],
            })
            hass.states.async_set(cost, "ready", {"free_window_source_ready": True})
            rendered = template.async_render(parse_result=False)
            assert "waiting, not washing" in rendered
            assert "Use the dishwasher controls" in rendered
            assert "The dishwasher is waiting on its own delayed-start timer" in rendered
            assert "Automatic programme cooldowns" not in rendered
            assert "Free-electricity pricing unavailable" not in rendered
            hass.states.async_remove(explanation)
            hass.states.async_remove(cost)
            hass.states.async_set(orchestration, "queued", {"request": {"program": "Eco50"}})
            rendered = template.async_render(parse_result=False)
            assert "Eco50 is queued for a start-time safety check" in rendered
            assert "Automatic programme cooldowns" not in rendered
            hass.states.async_remove(orchestration)
            rendered = template.async_render(parse_result=False)
            assert "Scheduling status is unavailable" in rendered
            print(f"{path}: scheduling reasons, native timer, cooldowns, timezone and older-version fallback passed")
        ev = yaml.safe_load((ROOT / "custom_components/load_optimizer/ev_dashboard.yaml").read_text())
        ev_cards = [card for card in cards(ev) if card.get("type") == "markdown"]
        for state, attributes in (
            ("unavailable", {}),
            ("ready", {"plan_status": "ready", "battery_percent": 0, "target_percent": 70,
                       "actual_power_w": 0, "meter_energy_kwh": None,
                       "selected_slots": [{"start": "2026-10-19T08:30:00+00:00", "end": "2026-10-19T09:00:00+00:00",
                                           "price_p_per_kwh": -15, "energy_kwh": 2.5, "cost_pence": -37.5}],
                       "sources": [{"role": "battery_entity", "status": "available", "age_seconds": 0}],
                       "control": {"state": "disabled", "reason": "disabled", "last_stop_reason": "charging_not_confirmed",
                                   "delivery": {"status": "charging_not_confirmed"}}}),
        ):
            hass.states.async_set("sensor.ev_charging_review", state, attributes)
            rendered = "\n".join(Template(card["content"], hass).async_render(parse_result=False) for card in ev_cards)
            assert "None" not in rendered, rendered
            if state == "ready":
                for text in ("0% to 70%", "09:30", "BST", "-15 p/kWh", "charging not confirmed", "0 W"):
                    assert text in rendered, (text, rendered)
        print("EV dashboard: ready/absent data, zero values, selected slots, home timezone and retained stop reasons passed")
        readiness = next(card for card in ev_cards if card.get("title") == "Source Readiness")
        assert "|---|---|---:|\n| battery |" in Template(readiness["content"], hass).async_render(parse_result=False), "Whitespace must not split the Markdown table"
        delivery_card = next(card for card in ev_cards if card.get("title") == "Control And Delivery")
        for warning in ("battery_gain_below_expected", None):
            feedback = {"status": "battery_gain_below_expected" if warning else "charging_confirmed"}
            if warning:
                feedback["warning"] = warning
            hass.states.async_set("sensor.ev_charging_review", "ready", {
                "charger_state": "on", "control": {"state": "enabled",
                    "reason": "charging_in_selected_slot", "delivery": feedback}})
            rendered = Template(delivery_card["content"], hass).async_render(parse_result=False)
            assert ("**Warning:**" in rendered) == bool(warning), rendered
            if warning:
                assert "does not stop charging" in rendered, rendered
        print("EV delivery warning: visible while charging and cleared after battery feedback recovers")
        hass.states.async_set("sensor.ev_charging_review", "ready", {
            "selected_slots": [{"start": "2026-10-21T14:00:00+00:00"}],
            "control": {"state": "enabled", "reason": "waiting_for_selected_slot",
                        "session_max_hours": 4, "session_max_energy_kwh": 0.3,
                        "session_energy_kwh": 0.01}})
        rendered = Template(delivery_card["content"], hass).async_render(parse_result=False)
        for text in ("Waiting for a cheaper", "15:00 BST", "4 hours", "0.3 kWh", "0.01 kWh"):
            assert text in rendered, (text, rendered)
        from homeassistant.components import input_boolean, input_number
        package = yaml.safe_load((ROOT / "dev/ev-test-package.yaml").read_text())
        input_number.CONFIG_SCHEMA({"input_number": package["input_number"]})
        input_boolean.CONFIG_SCHEMA({"input_boolean": package["input_boolean"]})
        hass.states.async_set("input_number.ev_trial_battery_percent", "0")
        hass.states.async_set("input_number.ev_trial_capacity_kwh", "0.6")
        hass.states.async_set("input_number.ev_trial_target_percent", "80")
        hass.states.async_set("input_boolean.ev_trial_connected", "off")
        hass.states.async_set("switch.ev_trial_load", "off")
        hass.states.async_set("sensor.ev_trial_load_power", "0")
        sensors = package["template"][0]["sensor"]
        values = {s["name"]: str(Template(s["state"], hass).async_render(parse_result=False)) for s in sensors}
        assert values["EV Trial Battery"] == "0"
        assert values["EV Trial Connection"] == "disconnected"
        assert values["EV Trial Charging Status"] == "idle"
        hass.states.async_set("switch.ev_trial_load", "on")
        hass.states.async_set("sensor.ev_trial_load_power", "60")
        status = next(s for s in sensors if s["name"] == "EV Trial Charging Status")
        assert Template(status["state"], hass).async_render(parse_result=False) == "charging"
        hass.states.async_set("sensor.ev_trial_load_power", "unavailable")
        assert not Template(status["availability"], hass).async_render()
        print("EV test helpers: safe defaults, zero battery, real-power status and unavailable source checks passed")
    assert styles[0] == styles[1], "Public and full dashboards must compare prices identically"
    assert scheduling_templates[0] == scheduling_templates[1], "Scheduling explanations must match across dashboards"


asyncio.run(main())
