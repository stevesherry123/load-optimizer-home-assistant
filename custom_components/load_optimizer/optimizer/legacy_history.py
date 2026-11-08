"""Explicit conversion of verified Octopus Intelligence cache records."""

from datetime import timedelta
import re
from zoneinfo import ZoneInfo

from .history_import import validate_import
from .intelligence import complete, days_from_slots, normalize, utc


def adapt_agile_buddy(records, *, history_tariff_code, target_tariff_code,
                     source_id, now, timezone_name="Europe/London", retention_days=90):
    """Convert period-end dt/r records, never inferring their tariff from prices."""
    if not isinstance(history_tariff_code, str) or not re.fullmatch(
        r"E-1R-AGILE-\d{2}-\d{2}-\d{2}-[A-HJ-NP]", history_tariff_code
    ) or history_tariff_code != target_tariff_code:
        raise ValueError("Verified historical and destination Agile tariffs must match")
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("Destination source identifier is required")
    if not isinstance(records, list) or not records or len(records) > 250000:
        raise ValueError("Expected a non-empty cache with at most 250000 records")
    periods = []
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("dt"), str):
            raise ValueError("Cache records require an offset-aware dt timestamp")
        price = record.get("r")
        if isinstance(price, bool) or not isinstance(price, (int, float)):
            raise ValueError("Cache r must be a numeric p/kWh price")
        end = utc(record["dt"])
        if end.minute not in (0, 30) or end.second or end.microsecond:
            raise ValueError("Cache periods must end on half-hour boundaries")
        periods.append({"start": end - timedelta(minutes=30), "end": end,
                        "price_p_per_kwh": price})
    slots = normalize(periods)
    days = days_from_slots(slots, timezone_name, source_id)
    today = utc(now).astimezone(ZoneInfo(timezone_name)).date()
    selected = [day for day in days
                if today - timedelta(days=retention_days) <= day.local_date < today]
    payload = {"schema": 1, "source_id": source_id, "timezone": timezone_name,
               "price_unit": "p_per_kwh", "days": [
                   {"date": day.local_date.isoformat(), "slots": [slot.as_dict() for slot in day.slots]}
                   for day in selected if complete(day)]}
    validate_import(payload, timezone_name=timezone_name, source=source_id,
                    today=today, retention_days=retention_days)
    report = {"records": len(records), "complete_days": len(payload["days"]),
              "incomplete_days": sum(not complete(day) for day in selected),
              "outside_retention_days": len(days) - len(selected),
              "tariff_code": target_tariff_code}
    return payload, report
