"""Exercise dashboard templates with the real minimum Home Assistant runtime."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template


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
        if value.get("type") == "tile":
            yield value
        for child in value.values():
            yield from cards(child)
    elif isinstance(value, list):
        for child in value:
            yield from cards(child)


async def main():
    styles = []
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
    assert styles[0] == styles[1], "Public and full dashboards must compare prices identically"


asyncio.run(main())
