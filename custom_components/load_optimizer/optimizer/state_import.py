"""Validate portable appliance memory before it reaches the live runtime."""

from __future__ import annotations

import json
import math
import re
from typing import Any

MAX_STATE_BYTES = 16 * 1024 * 1024
MAX_STATE_DEPTH = 32


def validate_import(payload: str | dict[str, Any]) -> dict[str, Any]:
    """Return a detached, finite JSON database or reject it without mutations."""
    if isinstance(payload, str):
        if len(payload) > MAX_STATE_BYTES or len(payload.encode("utf-8")) > MAX_STATE_BYTES:
            raise ValueError("Imported state exceeds the 16 MiB limit")
        try:
            data = json.loads(payload)
        except (ValueError, RecursionError) as error:
            raise ValueError("Imported state must be valid JSON") from error
    elif isinstance(payload, dict):
        try:
            encoded = json.dumps(payload, allow_nan=False)
        except (ValueError, TypeError, RecursionError) as error:
            raise ValueError("Imported state must contain finite JSON values") from error
        return validate_import(encoded)
    else:
        raise ValueError("Imported state must be a JSON database")

    def finite_json(value: Any, depth: int = 0) -> None:
        if depth > MAX_STATE_DEPTH:
            raise ValueError("Imported state is too deeply nested")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Imported state contains a non-finite number")
        if isinstance(value, dict):
            for item in value.values():
                finite_json(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                finite_json(item, depth + 1)

    finite_json(data)
    if not isinstance(data, dict) or not isinstance(data.get("instances"), dict):
        raise ValueError("Imported state must contain an instances object")
    version = data.setdefault("schema_version", 1)
    if isinstance(version, bool) or version != 1:
        raise ValueError("Imported state schema version is not supported")
    if len(data["instances"]) > 256:
        raise ValueError("Imported state contains too many instances")
    for instance_id, instance in data["instances"].items():
        if re.fullmatch(r"[a-z0-9_-]{1,64}", instance_id) is None or not isinstance(instance, dict):
            raise ValueError("Imported instances must have valid IDs and object values")
        models = instance.get("program_models", {})
        if not isinstance(models, dict) or len(models) > 256 or any(not isinstance(model, dict) for model in models.values()):
            raise ValueError("Imported program models must be objects")
        for value in (instance, *models.values()):
            runs = value.get("runs", 0)
            if isinstance(runs, bool) or not isinstance(runs, int) or runs < 0:
                raise ValueError("Imported run counts must be non-negative integers")
        for key in ("last_cycle", "last_discarded_cycle"):
            if instance.get(key) is not None and not isinstance(instance[key], dict):
                raise ValueError("Imported cycle summaries must be objects")
        for key in ("profile", "samples"):
            if key in instance and not isinstance(instance[key], list if key == "profile" else (int, float)):
                raise ValueError("Imported capture fields have invalid types")
    return data
