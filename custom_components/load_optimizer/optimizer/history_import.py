"""Validate portable tariff history before making any storage changes."""

from __future__ import annotations

from datetime import date, timedelta

from .intelligence import TariffDay, complete, normalize


def validate_import(payload: dict, *, timezone_name: str, source: str,
                    today: date, retention_days: int = 90) -> list[TariffDay]:
    if not isinstance(payload, dict) or payload.get("schema") != 1:
        raise ValueError("Import requires portable history schema 1")
    if payload.get("timezone") != timezone_name or payload.get("price_unit") != "p_per_kwh":
        raise ValueError("Import timezone and p/kWh units must match")
    if payload.get("source_id") != source:
        raise ValueError("Import tariff source must match; unverified history cannot be imported")
    rows = payload.get("days")
    if not isinstance(rows, list) or len(rows) > 365:
        raise ValueError("Import requires at most 365 day records")
    if not 1 <= retention_days <= 365:
        raise ValueError("Retention must be 1 to 365 days")
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each imported day must be an object")
        local_date = date.fromisoformat(row["date"])
        if local_date in seen:
            raise ValueError("Duplicate imported day")
        seen.add(local_date)
        slots = row.get("slots")
        if not isinstance(slots, list) or not 1 <= len(slots) <= 288:
            raise ValueError("Imported days require 1 to 288 slots")
        if any(isinstance(slot.get("price_p_per_kwh"), bool) for slot in slots if isinstance(slot, dict)):
            raise ValueError("Boolean prices are not valid tariff data")
        value = TariffDay(local_date, timezone_name, normalize(slots), source)
        if not complete(value):
            raise ValueError("Imported days must have complete, contiguous local coverage")
        if today - timedelta(days=retention_days) <= local_date < today:
            result.append(value)
    return result
