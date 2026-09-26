"""Small, dependency-free observability engine for community support."""

from __future__ import annotations

import json
import logging
import re
import threading
from collections import Counter, deque
from datetime import datetime, timezone
from typing import Any

SENSITIVE_KEY = re.compile(r"token|password|secret|authorization|api[_-]?key", re.I)


def _safe(value: Any, key: str = "") -> Any:
    """Return bounded, JSON-safe diagnostic data without credentials."""
    if SENSITIVE_KEY.search(key):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(k): _safe(v, str(k)) for k, v in list(value.items())[:20]}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value[:25]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        text = value
    else:
        text = str(value)
    return text[:250] if isinstance(text, str) else text


class EventEngine:
    """Emit searchable logs and retain a short, publishable diagnostic trail."""

    def __init__(self, logger: logging.Logger, history_size: int = 25) -> None:
        self.logger = logger
        self._events: deque[dict] = deque(maxlen=max(10, min(history_size, 50)))
        self._counts: Counter[str] = Counter()
        self._lock = threading.Lock()

    def emit(self, level: int, event: str, message: str, **context: Any) -> None:
        safe_context = _safe(context)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": logging.getLevelName(level).lower(),
            "event": event,
            "message": message,
            "context": safe_context,
        }
        with self._lock:
            self._counts[record["level"]] += 1
            if level >= logging.INFO:
                self._events.append(record)
        suffix = " ".join(
            f"{key}={json.dumps(value, separators=(',', ':'))}"
            for key, value in safe_context.items()
        )
        self.logger.log(level, "[%s] %s%s", event, message, f" | {suffix}" if suffix else "")

    def debug(self, event: str, message: str, **context: Any) -> None:
        self.emit(logging.DEBUG, event, message, **context)

    def info(self, event: str, message: str, **context: Any) -> None:
        self.emit(logging.INFO, event, message, **context)

    def warning(self, event: str, message: str, **context: Any) -> None:
        self.emit(logging.WARNING, event, message, **context)

    def error(self, event: str, message: str, **context: Any) -> None:
        self.emit(logging.ERROR, event, message, **context)

    def exception(self, event: str, message: str, **context: Any) -> None:
        self.emit(logging.ERROR, event, message, **context)
        self.logger.debug("Exception details for %s", event, exc_info=True)

    def snapshot(self) -> dict:
        with self._lock:
            events = list(self._events)
            counts = dict(self._counts)
        return {
            "event_counts": counts,
            "recent_events": events,
            "last_error": next(
                (item for item in reversed(events) if item["level"] == "error"),
                None,
            ),
            "event_code_help": (
                "Search the app log for the event code in square brackets "
                "when requesting support."
            ),
        }


def configure_logging(level_name: str = "info") -> logging.Logger:
    """Configure predictable stdout logging for Home Assistant collection."""
    aliases = {"trace": logging.DEBUG, "notice": logging.INFO, "fatal": logging.CRITICAL}
    level = aliases.get(level_name.lower(), getattr(logging, level_name.upper(), logging.INFO))
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        force=True,
    )
    return logging.getLogger("load_optimizer")
