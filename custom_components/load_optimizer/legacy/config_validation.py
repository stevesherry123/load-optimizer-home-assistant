"""Bounded appliance configuration parsing and pre-save checks, without HA I/O."""

from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from functools import lru_cache
import math
import re
import textwrap
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from yaml.events import AliasEvent

from .costing import SCHEDULE_STRATEGIES, WINDOW_PREFERENCES

MAX_CONFIG_BYTES = 131_072
MAX_APPLIANCES = 64
MAX_POLICIES = 128
ENTITY_ID = re.compile(r"[a-z_][a-z0-9_]*\.[a-z0-9_]+\Z")
LOCAL_TIME = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d\Z")
WRAPPED_OPTION_KEYS = {
    "blocked_window_entity", "cost_candidate_interval", "cost_forecast_hours",
    "cost_forecast_interval", "cost_search_hours", "green_window_entity",
    "instances_yaml", "publish_cost_forecast", "publish_diagnostics",
    "publish_profile_data", "scan_interval", "schedule_preference_weight_pence",
    "tariff_entities", "tariff_entity", "tariff_price_unit", "tariff_timezone",
    "log_history", "log_level", "reset_instance_ids",
}


class ConfigurationError(ValueError):
    """A safe, generated field error that never includes the pasted document."""

    def __init__(self, field: str, detail: str) -> None:
        super().__init__(detail)
        self.field = field


class _ConfigLoader(yaml.SafeLoader):
    """Reject aliases, duplicate keys and excessive nesting before construction."""

    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self._depth = 0
        self._nodes = 0

    def compose_node(self, parent, index):
        if self.check_event(AliasEvent):
            raise ConfigurationError("instances_yaml", "YAML aliases are not supported.")
        self._nodes += 1
        self._depth += 1
        try:
            if self._nodes > 20_000 or self._depth > 16:
                raise ConfigurationError("instances_yaml", "The appliance document is too complex.")
            return super().compose_node(parent, index)
        finally:
            self._depth -= 1

    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise ConfigurationError("instances_yaml", "Use unique text keys in each mapping.")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


# Keep legacy times, IDs and words such as On literal; use explicit booleans.
_ConfigLoader.yaml_implicit_resolvers = {
    key: [(tag, pattern) for tag, pattern in resolvers if tag not in {
        "tag:yaml.org,2002:int", "tag:yaml.org,2002:bool", "tag:yaml.org,2002:timestamp",
    }]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_ConfigLoader.add_implicit_resolver(
    "tag:yaml.org,2002:int", re.compile(r"[-+]?(?:0|[1-9][0-9]*)\Z"), list("-+0123456789"),
)
_ConfigLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"(?:true|false)\Z", re.IGNORECASE), list("tTfF"),
)


def _document(raw: object) -> object:
    if isinstance(raw, list):
        return raw
    try:
        within_limit = isinstance(raw, str) and len(raw.encode("utf-8")) <= MAX_CONFIG_BYTES
    except UnicodeError:
        within_limit = False
    if not within_limit:
        raise ConfigurationError("instances_yaml", "Use an appliance list of at most 128 KiB.")
    return deepcopy(_decoded_document(raw))


@lru_cache(maxsize=4)
def _decoded_document(raw: str) -> object:
    """Reuse bounded parses across scans; callers receive independent copies."""
    loader = _ConfigLoader(textwrap.dedent(raw))
    try:
        return loader.get_single_data()
    except ConfigurationError:
        raise
    except (yaml.YAMLError, ValueError, OverflowError, RecursionError) as error:
        raise ConfigurationError("instances_yaml", "Check YAML syntax and indentation.") from error
    finally:
        loader.dispose()


def appliance_document(raw: object) -> tuple[list[dict], dict[str, Any]]:
    """Read block YAML, JSON, an instances wrapper or legacy add-on options."""
    parsed = _document(raw)
    wrapped = {}
    if isinstance(parsed, dict):
        if "instances_yaml" in parsed:
            wrapped = {key: value for key, value in parsed.items() if key in WRAPPED_OPTION_KEYS}
            parsed = _document(parsed["instances_yaml"])
        if isinstance(parsed, dict) and set(parsed) == {"instances"}:
            parsed = parsed["instances"]
    if not isinstance(parsed, list) or len(parsed) > MAX_APPLIANCES:
        raise ConfigurationError("instances_yaml", "Use a list containing at most 64 appliances.")
    if any(not isinstance(item, dict) for item in parsed):
        raise ConfigurationError("instances_yaml", "Every appliance must be a mapping of settings.")
    return parsed, wrapped


def effective_options(options: dict[str, Any]) -> dict[str, Any]:
    """Apply the same split-field precedence as the compatibility adapter."""
    _, wrapped = appliance_document(options.get("instances_yaml", ""))
    result = dict(options)
    for key, value in wrapped.items():
        current = result.get(key)
        if key == "instances_yaml" or current is None or str(current).strip() in {
            "", "unknown", "unavailable", "none", "None",
        }:
            result[key] = value
    return result


def _number(values, key, minimum, maximum, *, integer=False, field="instances_yaml", label=""):
    if key not in values:
        return
    value = values[key]
    try:
        number = float(value)
        if isinstance(value, bool) or not math.isfinite(number) or not minimum <= number <= maximum:
            raise ValueError
        if integer and (not number.is_integer() or isinstance(value, str) and not value.strip().isdigit()):
            raise ValueError
    except (TypeError, ValueError, OverflowError) as error:
        kind = "whole number" if integer else "finite number"
        raise ConfigurationError(field, f"{label}{key}: use a {kind} from {minimum:g} to {maximum:g}.") from error


def _entity(value, field, *, required=False, sensor=False, multiple=False):
    if value in (None, "") and not required:
        return
    if multiple and isinstance(value, str):
        for item in value.split(","):
            _entity(item.strip(), field, required=True, sensor=sensor)
        return
    if not isinstance(value, str) or not ENTITY_ID.fullmatch(value.strip()):
        raise ConfigurationError(field, "Use complete entity IDs such as sensor.appliance_power.")
    if sensor and not value.strip().startswith("sensor."):
        raise ConfigurationError(field, "Power and energy sources must be sensor entities.")


@dataclass(frozen=True)
class ApplianceConfiguration:
    """Validated effective configuration, without changing the saved document."""

    instances: list[dict]
    options: dict[str, Any]


def validate_appliance_options(options: dict[str, Any]) -> ApplianceConfiguration:
    """Validate only on explicit setup/edit; never rewrite existing learning."""
    from .app_runtime import instance_config_from_entry, normalise_program, normalise_program_policy

    options = effective_options(options)
    entries, _ = appliance_document(options.get("instances_yaml", ""))
    if not entries:
        raise ConfigurationError("instances_yaml", "Configure at least one appliance.")
    if options.get("reset_instance_ids"):
        raise ConfigurationError("instances_yaml", "Remove reset_instance_ids before saving appliance settings.")
    try:
        ZoneInfo(options.get("tariff_timezone", "Europe/London"))
    except (ZoneInfoNotFoundError, ValueError, TypeError) as error:
        raise ConfigurationError("tariff_timezone", "Enter a valid timezone such as Europe/London.") from error
    if options.get("tariff_price_unit", "p_per_kwh") not in ("p_per_kwh", "gbp_per_kwh"):
        raise ConfigurationError("tariff_price_unit", "Choose p_per_kwh or gbp_per_kwh.")
    for key, bounds in {
        "scan_interval": (10, 3600), "cost_search_hours": (1, 72),
        "cost_forecast_hours": (1, 72), "cost_forecast_interval": (5, 60),
        "cost_candidate_interval": (1, 30),
    }.items():
        _number(options, key, *bounds, integer=True, field=key)
    _number(options, "schedule_preference_weight_pence", 0, 10,
            field="schedule_preference_weight_pence")
    for key in ("tariff_entity", "green_window_entity", "blocked_window_entity"):
        _entity(options.get(key), key, multiple=key != "tariff_entity")
    tariffs = options.get("tariff_entities", "")
    if not isinstance(tariffs, (str, list)):
        raise ConfigurationError("tariff_entities", "Use comma-separated tariff entity IDs.")
    for entity_id in tariffs.split(",") if isinstance(tariffs, str) else tariffs:
        _entity(entity_id, "tariff_entities")

    ids = set()
    configs = []
    for index, entry in enumerate(entries, start=1):
        label = f"Appliance {index}: "
        instance_id = entry.get("id", entry.get("instance_id", index))
        if isinstance(instance_id, bool) or re.fullmatch(r"[0-9]{1,32}", str(instance_id).strip()) is None or int(instance_id) <= 0:
            raise ConfigurationError("instances_yaml", label + "use a positive numeric ID.")
        instance_id = str(instance_id).strip()
        if "id" in entry and "instance_id" in entry and str(entry["instance_id"]).strip() != instance_id:
            raise ConfigurationError("instances_yaml", label + "id and instance_id must match when both are supplied.")
        if instance_id in ids:
            raise ConfigurationError("instances_yaml", label + "each appliance must have a distinct ID.")
        ids.add(instance_id)
        for key in ("power_sensor", "energy_sensor", "program_sensor", "state_sensor",
                    "schedule_earliest_start_entity", "schedule_latest_finish_entity",
                    "green_window_entity", "blocked_window_entity"):
            _entity(entry.get(key), "instances_yaml", required=key == "power_sensor",
                    sensor=key in {"power_sensor", "energy_sensor"},
                    multiple=key in {"green_window_entity", "blocked_window_entity"})
        for key, (minimum, maximum, integer) in {
            "active_power_threshold": (0, 100_000, False), "finish_delay": (1, 3600, True),
            "learning_min_runtime_minutes": (0, 10_080, False), "learning_min_samples": (1, 10_000, True),
            "learning_min_energy_kwh": (0, 10_000, False), "schedule_confidence_threshold": (0, 100, True),
            "schedule_start_tolerance_minutes": (0, 1440, True),
            "schedule_equivalent_cost_tolerance_pence": (0, 100_000, False),
            "schedule_preference_weight_pence": (0, 10, False),
        }.items():
            _number(entry, key, minimum, maximum, integer=integer, label=label)
        for key, allowed in (("schedule_strategy", SCHEDULE_STRATEGIES),
                             ("schedule_window_preference", WINDOW_PREFERENCES)):
            if key in entry and (not isinstance(entry[key], str) or entry[key] not in allowed):
                raise ConfigurationError("instances_yaml", label + f"choose a supported {key}.")
        for key in ("schedule_overnight_start", "schedule_overnight_end"):
            if key in entry and (not isinstance(entry[key], str) or not LOCAL_TIME.fullmatch(entry[key])):
                raise ConfigurationError("instances_yaml", label + f"{key}: use local HH:MM.")
        policies = entry.get("program_policies", [])
        if not isinstance(policies, list) or len(policies) > MAX_POLICIES:
            raise ConfigurationError("instances_yaml", label + "use a list of at most 128 programme policies.")
        programs = set()
        for policy in policies:
            if not isinstance(policy, dict) or not isinstance(policy.get("program"), str):
                raise ConfigurationError("instances_yaml", label + "each policy requires a programme name.")
            program = normalise_program(policy["program"])
            if program == "unknown" or not program.strip() or program in programs:
                raise ConfigurationError("instances_yaml", label + "use distinct, non-empty programme names.")
            programs.add(program)
            for key in ("enabled", "allow_normal_recommendation", "allow_negative_price_run"):
                if key in policy and not isinstance(policy[key], bool):
                    raise ConfigurationError("instances_yaml", label + f"{key}: use true or false, without quotes.")
            for key in ("preference_rank", "negative_price_priority", "minimum_days_between_runs",
                        "minimum_hours_between_runs", "maximum_runs_per_window"):
                _number(policy, key, 1 if key.endswith(("rank", "priority")) else 0,
                        100 if key.endswith(("rank", "priority")) else 100_000, integer=True, label=label)
            for key in ("fixed_cost_pence", "estimated_overhead_cost_pence", "water_litres",
                        "water_cost_pence_per_litre", "wear_cost_pence"):
                _number(policy, key, 0, 100_000, label=label)
            try:
                normalise_program_policy(policy)
            except (TypeError, ValueError, OverflowError) as error:
                raise ConfigurationError("instances_yaml", label + "check programme classification and costs.") from error
        configs.append(instance_config_from_entry(entry, index, options))
    return ApplianceConfiguration(configs, options)
