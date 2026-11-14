"""Render every beta Markdown template without any live HA or physical controls."""

import asyncio
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import yaml
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dev.build_dashboard_beta import build, walk, OUTPUT


async def main():
    assert yaml.safe_load(OUTPUT.read_text()) == build(), "Regenerate the beta YAML"
    dashboard = build()
    assert [view["path"] for view in dashboard["views"]] == ["overview", "dishwasher", "learning", "diagnostics"]
    actions = [node for node in walk(dashboard) if node.get("action") == "perform-action"]
    assert len(actions) == 4 and all(node.get("confirmation") for node in actions)
    assert dashboard["views"][-1]["sections"][-1]["cards"][-1]["title"] == "Automation Capabilities"
    assert {action["target"]["entity_id"] for action in actions} == {
        "button.load_optimizer_1_request_overnight", "button.load_optimizer_1_request_now",
        "button.load_optimizer_1_cancel_schedule", "button.load_optimizer_1_request_now_override"}
    entity_ids = {node.get("entity") for node in walk(dashboard)}
    assert {"time.load_optimizer_1_overnight_start", "time.load_optimizer_1_overnight_end",
            "number.load_optimizer_1_door_open_minimum_minutes"} <= entity_ids

    with TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
        hass.config.skip_pip = True
        dt_util.set_default_time_zone(await dt_util.async_get_time_zone("Europe/London"))
        try:
            templates = [card for card in walk(dashboard) if card.get("type") == "markdown"]
            for populated in (False, True):
                if populated:
                    hass.states.async_set("sensor.load_optimizer_1_orchestration_status", "idle", {
                        "last_program": "Quick45", "last_result": "completed",
                        "last_attempt": "2026-10-27T04:00:00+00:00",
                        "last_message": "Completed | checked", "request": None})
                    hass.states.async_set("sensor.load_optimizer_1_automation_explanation", "waiting", {
                        "summary": "Waiting for a load", "blockers": ["door_not_opened_since_last_cycle"],
                        "recent_events": [{"timestamp": "2026-10-27T04:31:00Z", "event": "completed", "program": "Quick45"}]})
                    hass.states.async_set("sensor.load_optimizer_1_last_finish", "2026-10-27T04:31:00Z")
                for card in templates:
                    rendered = Template(card["content"], hass).async_render(parse_result=False)
                    assert isinstance(rendered, str), card["title"]
                    if card["title"] == "Scheduling" and populated:
                        assert "Readiness checks are pending" in rendered and "No outstanding" not in rendered
                    if card["title"] == "Next wash":
                        assert ("No wash queued" if populated else "Scheduling status unavailable") in rendered
                    if card["title"] == "Execution record":
                        assert "| Recommendation estimate | Not recorded |" in rendered
                        assert "Estimate window" not in rendered
                        assert "Other programme estimates" not in rendered
                        if populated:
                            assert "Quick45" in rendered and "completed" in rendered and "04:00 GMT" in rendered
                            assert rendered.startswith("| Record | Value |\n|---|---|"), rendered
            execution = next(card for card in templates if card["title"] == "Execution record")
            for price in (-0.5, 0, 12.25):
                hass.states.async_set("sensor.load_optimizer_1_orchestration_status", "confirmed", {
                    "last_attempt": "2026-10-27T04:03:00Z",
                    "last_start_decision_snapshot": {"request": {"recommendation_quote": {
                        "program": "Quick45", "estimated_cost_pence": price,
                        "start": "2026-10-27T04:00:00Z", "finish": "2026-10-27T04:30:00Z",
                    }, "recommendation_alternatives": [{
                        "program": "Eco50", "estimated_cost_pence": 0,
                        "start": "2026-10-27T04:10:00Z", "finish": "2026-10-27T08:30:00Z",
                    }]}}})
                rendered = Template(execution["content"], hass).async_render(parse_result=False)
                assert f"| Recommendation estimate | {price:.2f} p |" in rendered
                assert "| Estimate window | Tue 27 Oct 04:00 GMT to Tue 27 Oct 04:30 GMT |\n| Result" in rendered, rendered
                assert "| Last start | Tue 27 Oct 04:03 GMT |" in rendered
                assert "| Eco50 | 0.00 p | Tue 27 Oct 04:10 GMT to Tue 27 Oct 08:30 GMT |" in rendered
            hass.states.async_set("sensor.load_optimizer_1_orchestration_status", "queued", {"request": {
                "program": "MixedLoad", "start": "2026-10-28T22:00:00Z", "finish": "2026-10-29T00:00:00Z", "cost_pence": 40}})
            card = next(card for card in templates if card["title"] == "Next wash")
            rendered = Template(card["content"], hass).async_render(parse_result=False)
            assert "MixedLoad queued" in rendered and "GBP 0.40" in rendered and "GMT" in rendered
            # Every phase renders distinctly, even when an old plan is retained
            # during a price outage. The two dashboards share this exact card.
            full = yaml.safe_load((ROOT / "homeassistant/dashboards/full/load_optimizer_dashboard.yaml").read_text())
            assert next(card for card in walk(full) if card.get("title") == "Next wash")["content"].strip() == card["content"].strip()
            pending = {"normal_wash": True, "program": "MixedLoad", "start": "2026-10-28T22:00:00Z",
                       "finish": "2026-10-29T08:30:00Z", "late_finish": True,
                       "window_start": "2026-10-28T21:00:00Z", "window_end": "2026-10-29T07:00:00Z"}
            for phase, expected in (("awaiting_plan", "One wash authorised; waiting for a plan"),
                                    ("queued", "MixedLoad queued"), ("commanding", "Running has not been confirmed")):
                hass.states.async_set("sensor.load_optimizer_1_orchestration_status", phase, {"request": pending})
                hass.states.async_set("sensor.load_optimizer_1_automation_explanation", "waiting", {
                    "request_state": phase, "summary": "Waiting for complete prices.", "running_confirmed": False})
                rendered = Template(card["content"], hass).async_render(parse_result=False)
                assert expected in rendered and "authorised start window" in rendered.lower(), rendered
                assert "GMT" in rendered and "One normal wash is authorised" in rendered
                if phase == "awaiting_plan":
                    assert "MixedLoad queued" not in rendered and "No start is queued" in rendered
                if phase == "queued":
                    assert "Later finish" in rendered and "finishes afterwards" in rendered
            hass.states.async_set("sensor.load_optimizer_1_automation_explanation", "running", {
                "running_confirmed": True, "summary": "The dishwasher has confirmed it is washing."})
            rendered = Template(card["content"], hass).async_render(parse_result=False)
            assert "Dishwasher is washing" in rendered and "MixedLoad queued" not in rendered
            hass.states.async_set("sensor.load_optimizer_1_orchestration_status", "cancelled", {"request": None})
            hass.states.async_set("sensor.load_optimizer_1_automation_explanation", "cancelled", {
                "running_confirmed": False, "summary": "Pending request cancelled. An active wash is not stopped."})
            rendered = Template(card["content"], hass).async_render(parse_result=False)
            assert "No wash queued" in rendered and "cancelled" in rendered
            hass.states.async_set("sensor.load_optimizer_1_automation_explanation", "waiting", {
                "blocker_messages": ["Close the dishwasher door before a wash can start."],
                "warning_messages": ["A request is already pending."], "blockers": ["door_open"]})
            schedule = next(item for item in templates if item["title"] == "Scheduling")
            rendered = Template(schedule["content"], hass).async_render(parse_result=False)
            assert "Close the dishwasher door" in rendered and "door_open" not in rendered
            economics = next(card for card in templates if card["title"] == "Cycle costs")
            hass.states.async_set("sensor.load_optimizer_1_negative_price_recommendation", "Quick45", {
                "status": "ready", "program": "Quick45", "net_benefit_pence": 0.000001,
                "operating_cost_breakdown": {"energy_cost_pence": -0.000001, "total_cost_pence": -0.000001},
                "unconfigured_costs": ["consumables_cost_pence", "wear_cost_pence"]})
            rendered = Template(economics["content"], hass).async_render(parse_result=False)
            assert "less than 0.01" in rendered and "consumables, wear" in rendered
            assert "treated as zero" in rendered
            print(f"{len(templates)} beta Markdown cards passed missing/live-state fixtures; queue, UK time and confirmed actions passed")
        finally:
            await hass.async_stop()


asyncio.run(main())
