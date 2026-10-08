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
        self.loaded = False
        self.lock = asyncio.Lock()
        self.storage_error = None

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
        except Exception as error:
            self.storage_error = type(error).__name__
            LOGGER.exception("Tariff history could not be loaded; preserved without overwrite")
        self.loaded = True

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
            today = now.astimezone(ZoneInfo(self.timezone_name)).date()
            for day in observed:
                if not complete(day) or not today - timedelta(days=365) <= day.local_date <= today + timedelta(days=1):
                    continue
                old = candidate.get(day.local_date.isoformat())
                if old is None or old.fingerprint != day.fingerprint:
                    candidate[day.local_date.isoformat()] = day
                    changed = True
            retained = {key: day for key, day in candidate.items() if today - timedelta(days=365) <= day.local_date <= today + timedelta(days=1)}
            changed = changed or retained.keys() != candidate.keys()
            if changed and not self.storage_error:
                try:
                    await self.store.async_save({"schema": 1, "days": {key: day.as_dict() for key, day in retained.items()}})
                    self.days = retained
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
