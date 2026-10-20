"""One-time cleanup of saved Octopus calendar references, not runtime fallback."""

import re

import yaml

MINIMUM_OCTOPUS_VERSION = "19.2.1"
ENTITY_ID = re.compile(r"(?:sensor|event|calendar)\.[a-z0-9_]+")


def clean_calendar_settings(settings: dict, depth: int = 0) -> dict:
    """Preserve unrelated settings and migrate both wrapped and per-load YAML."""
    if depth > 8:
        raise ValueError("Appliance configuration nesting exceeds the supported limit")
    result = dict(settings)
    for key in ("green_window_entity", "blocked_window_entity"):
        value = result.get(key)
        if not isinstance(value, str):
            continue
        entities = []
        for entity in value.split(","):
            entity = entity.strip()
            if key == "green_window_entity" and entity.endswith("_greener_nights"):
                continue
            if key == "blocked_window_entity" and entity.endswith("_octoplus_saving_sessions"):
                entity = entity.removesuffix("_octoplus_saving_sessions") + "_octoplus_power_down"
            entities.append(entity)
        updated = ",".join(dict.fromkeys(entities))
        if updated != value and ("_greener_nights" in value or "_octoplus_saving_sessions" in value):
            result[key] = updated
    raw = result.get("instances_yaml")
    if isinstance(raw, str) and ("_greener_nights" in raw or "_octoplus_saving_sessions" in raw):
        if len(raw) > 2_000_000:
            raise ValueError("Appliance configuration exceeds the supported size")
        document = yaml.safe_load(raw)
        if isinstance(document, dict):
            cleaned = clean_calendar_settings(document, depth + 1)
        elif isinstance(document, list) and all(isinstance(item, dict) for item in document):
            cleaned = [clean_calendar_settings(item, depth + 1) for item in document]
        else:
            raise ValueError("Appliance configuration must contain a mapping or appliance list")
        if cleaned != document:
            result["instances_yaml"] = yaml.safe_dump(cleaned, sort_keys=False, allow_unicode=True)
    return result


def configured_entities(settings: dict) -> set[str]:
    """Include entity references in structured options and wrapped YAML."""
    return set(ENTITY_ID.findall(str(settings)))
