"""Shared source-scoped tariff history, isolated from appliance learning."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from zoneinfo import ZoneInfo

from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .optimizer.intelligence import TariffDay, analyse, complete, days_from_slots, normalize
from .optimizer.tariffs import tariff_periods_from_entity
from .optimizer.history_import import validate_import

LOGGER = logging.getLogger(__name__)


def source_settings(data: dict) -> tuple[list[str], str, str]:
    raw = data.get("tariff_entities") or data.get("tariff_entity") or ""
    entities = sorted(set(raw if isinstance(raw, list) else [v.strip() for v in str(raw).split(",") if v.strip()]))
    return entities, data.get("tariff_timezone") or "Europe/London", data.get("tariff_price_unit") or "gbp_per_kwh"


def get_service(hass, data: dict):
    settings = source_settings(data)
    source_id = hashlib.sha256(json.dumps(settings).encode()).hexdigest()[:24]
    registry = hass.data.setdefault(f"{DOMAIN}_tariff_services", {})
    if source_id not in registry:
        registry[source_id] = TariffIntelligence(hass, source_id, *settings)
    return registry[source_id]


class TariffIntelligence:
    """Retain complete observed days and publish bounded analysis."""

    def __init__(self, hass, source_id, entity_ids, timezone_name, price_unit):
        self.hass = hass
        self.source_id = source_id
        self.entity_ids = entity_ids
        self.timezone_name = timezone_name
        self.price_unit = price_unit
        self.store = Store(hass, 1, f"{DOMAIN}.tariff_history.{source_id}")
        self.days = {}
        self.origins = {}
        self.loaded = False
        self.lock = asyncio.Lock()
        self.storage_error = None
        self.read_only = False

    async def async_load(self):
        if self.loaded:
            return
        try:
            payload = await self.store.async_load()
            if payload is not None:
                if payload.get("schema") != 1 or not isinstance(payload.get("days"), dict):
                    raise ValueError("Unsupported tariff history schema")
                days = {key: TariffDay.from_dict(value) for key, value in payload["days"].items()}
                if any(key != day.local_date.isoformat() or day.source != self.source_id
                       or day.timezone_name != self.timezone_name for key, day in days.items()):
                    raise ValueError("Tariff history source mismatch")
                self.days = days
                origins = payload.get("origins", {})
                if not isinstance(origins, dict) or any(value not in {"live", "import"} for value in origins.values()):
                    raise ValueError("Invalid tariff-history provenance")
                self.origins = {key: origins.get(key, "live") for key in days}
        except Exception as error:
            self.storage_error = type(error).__name__
            self.read_only = True
            LOGGER.exception("Tariff history could not be loaded; preserved without overwrite")
        self.loaded = True

    async def async_export(self, retention_days=90):
        """Return an explicit portable export, never entity attributes."""
        async with self.lock:
            await self.async_load()
            if self.storage_error:
                raise ValueError("Tariff history storage is not healthy")
            today = datetime.now(timezone.utc).astimezone(ZoneInfo(self.timezone_name)).date()
            selected = [day for key, day in sorted(self.days.items())
                        if today - timedelta(days=retention_days) <= day.local_date < today]
            return {"schema": 1, "timezone": self.timezone_name, "price_unit": "p_per_kwh",
                    "days": [{"date": day.local_date.isoformat(), "slots": [slot.as_dict() for slot in day.slots]}
                             for day in selected]}

    async def async_import(self, payload, *, dry_run=True, overwrite_live=False,
                           retention_days=90, now=None):
        """Validate all rows before an atomic, explicitly requested import."""
        async with self.lock:
            await self.async_load()
            if self.storage_error:
                raise ValueError("Tariff history storage is not healthy")
            today = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(self.timezone_name)).date()
            rows = validate_import(payload, timezone_name=self.timezone_name,
                                   source=self.source_id, today=today, retention_days=retention_days)
            candidate, origins = dict(self.days), dict(self.origins)
            report = {"dry_run": dry_run, "imported": 0, "replaced": 0, "skipped": 0,
                      "blocked_live": 0, "rejected": 0,
                      "outside_retention": len(payload["days"]) - len(rows)}
            for day in rows:
                key = day.local_date.isoformat()
                old = candidate.get(key)
                if old and old.fingerprint == day.fingerprint:
                    report["skipped"] += 1
                elif old and origins.get(key, "live") == "live" and not overwrite_live:
                    report["blocked_live"] += 1
                else:
                    candidate[key] = day
                    origins[key] = "import"
                    report["replaced" if old else "imported"] += 1
            if not dry_run and report["imported"] + report["replaced"]:
                await self.store.async_save({"schema": 1, "days": {key: day.as_dict() for key, day in candidate.items()},
                                             "origins": origins})
                self.days, self.origins = candidate, origins
            return report

    async def async_status(self, benchmark: dict, now: datetime | None = None) -> dict:
        async with self.lock:
            await self.async_load()
            now = now or datetime.now(timezone.utc)
            periods, errors = [], []
            for entity_id in self.entity_ids:
                state = self.hass.states.get(entity_id)
                try:
                    periods.extend(tariff_periods_from_entity(
                        {"attributes": dict(state.attributes)} if state else {},
                        reference_utc=now, timezone_name=self.timezone_name, price_unit=self.price_unit))
                except (ValueError, TypeError, KeyError):
                    errors.append("source_unavailable")
            try:
                slots = normalize(periods)
            except (ValueError, TypeError, KeyError):
                return {"status": "error", "data_quality": "invalid_slots", "summary": "Conflicting or invalid tariff periods; history preserved."}
            current_cap = benchmark.get("unit_rate_p_per_kwh") if benchmark.get("status") == "ready" else None
            observed = days_from_slots(slots, self.timezone_name, self.source_id, current_cap)
            changed = False
            candidate = dict(self.days)
            origins = dict(self.origins)
            today = now.astimezone(ZoneInfo(self.timezone_name)).date()
            for day in observed:
                if not complete(day) or not today - timedelta(days=365) <= day.local_date <= today + timedelta(days=1):
                    continue
                old = candidate.get(day.local_date.isoformat())
                if old is None or old.fingerprint != day.fingerprint or origins.get(day.local_date.isoformat()) == "import":
                    candidate[day.local_date.isoformat()] = day
                    origins[day.local_date.isoformat()] = "live"
                    changed = True
            retained = {key: day for key, day in candidate.items() if today - timedelta(days=365) <= day.local_date <= today + timedelta(days=1)}
            changed = changed or retained.keys() != candidate.keys()
            if changed and not self.read_only:
                try:
                    origins = {key: origins.get(key, "live") for key in retained}
                    await self.store.async_save({"schema": 1, "days": {key: day.as_dict() for key, day in retained.items()}, "origins": origins})
                    self.days = retained
                    self.origins = origins
                    self.storage_error = None
                except Exception as error:
                    self.storage_error = type(error).__name__
                    LOGGER.exception("Tariff history save failed; previous history retained")
            result = analyse(slots, list(self.days.values()), now=now,
                             timezone_name=self.timezone_name, source=self.source_id)
            result["data_quality"] = "storage_error" if self.storage_error else "partial_sources" if errors else "complete" if result["tomorrow_complete"] else "waiting_for_tomorrow"
            result["storage"] = {"schema": 1, "day_count": len(self.days),
                                 "first_day": min(self.days, default=None), "last_day": max(self.days, default=None),
                                 "source_id": self.source_id, "error": self.storage_error}
            if self.storage_error:
                result["status"] = "limited"
            return result
