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
    assert len(actions) == 2 and all(node.get("confirmation") for node in actions)
    assert dashboard["views"][-1]["sections"][-1]["cards"][-1]["title"] == "Automation Capabilities"
    with TemporaryDirectory() as directory:
        hass = HomeAssistant(directory)
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
                    if card["title"] == "Next wash":
                        assert ("No wash queued" if populated else "Scheduling status unavailable") in rendered
                    if card["title"] == "Execution record" and populated:
                        assert "Quick45" in rendered and "completed" in rendered and "04:00 GMT" in rendered
                        assert rendered.startswith("| Record | Value |\n|---|---|"), rendered
            hass.states.async_set("sensor.load_optimizer_1_orchestration_status", "queued", {"request": {
                "program": "MixedLoad", "start": "2026-10-28T22:00:00Z", "finish": "2026-10-29T00:00:00Z", "cost_pence": 40}})
            card = next(card for card in templates if card["title"] == "Next wash")
            rendered = Template(card["content"], hass).async_render(parse_result=False)
            assert "MixedLoad queued" in rendered and "GBP 0.40" in rendered and "GMT" in rendered
            print(f"{len(templates)} beta Markdown cards passed missing/live-state fixtures; queue, UK time and confirmed actions passed")
        finally:
            await hass.async_stop()


asyncio.run(main())
