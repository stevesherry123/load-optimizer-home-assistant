"""Pure, provider-neutral tariff history and deterministic analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import math
import statistics
from zoneinfo import ZoneInfo


def utc(value: datetime | str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Tariff timestamps require an explicit timezone")
    return result.astimezone(timezone.utc)


@dataclass(frozen=True)
class TariffSlot:
    start: datetime
    end: datetime
    price: float

    def __post_init__(self):
        if self.start != utc(self.start) or self.end != utc(self.end):
            raise ValueError("Tariff timestamps must be UTC")
        if self.end <= self.start or not math.isfinite(self.price):
            raise ValueError("Invalid tariff duration or price")

    def as_dict(self) -> dict:
        return {"start": self.start.isoformat(), "end": self.end.isoformat(), "price_p_per_kwh": self.price}


@dataclass(frozen=True)
class TariffDay:
    local_date: date
    timezone_name: str
    slots: tuple[TariffSlot, ...]
    source: str
    benchmark: float | None = None

    @property
    def fingerprint(self) -> str:
        payload = [self.local_date.isoformat(), self.timezone_name, self.source, [s.as_dict() for s in self.slots]]
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def as_dict(self) -> dict:
        return {"date": self.local_date.isoformat(), "timezone": self.timezone_name,
                "source": self.source, "slots": [s.as_dict() for s in self.slots],
                "fingerprint": self.fingerprint, "benchmark_p_per_kwh": self.benchmark}

    @classmethod
    def from_dict(cls, value: dict) -> TariffDay:
        day = cls(date.fromisoformat(value["date"]), value["timezone"],
                  normalize(value["slots"]), value["source"], value.get("benchmark_p_per_kwh"))
        if not complete(day) or value.get("fingerprint") != day.fingerprint:
            raise ValueError("Invalid or modified stored tariff day")
        if day.benchmark is not None and not math.isfinite(float(day.benchmark)):
            raise ValueError("Invalid stored benchmark")
        return day


def normalize(periods: list[dict]) -> tuple[TariffSlot, ...]:
    by_start = {}
    for period in periods:
        slot = TariffSlot(utc(period["start"]), utc(period["end"]), float(period["price_p_per_kwh"]))
        if slot.start in by_start and by_start[slot.start] != slot:
            raise ValueError("Conflicting duplicate tariff slots")
        by_start[slot.start] = slot
    slots = tuple(sorted(by_start.values(), key=lambda slot: slot.start))
    if any(left.end > right.start for left, right in zip(slots, slots[1:])):
        raise ValueError("Overlapping tariff slots")
    return slots


def bounds(local_date: date, timezone_name: str) -> tuple[datetime, datetime]:
    zone = ZoneInfo(timezone_name)
    return (datetime.combine(local_date, time.min, zone).astimezone(timezone.utc),
            datetime.combine(local_date + timedelta(days=1), time.min, zone).astimezone(timezone.utc))


def complete(day: TariffDay) -> bool:
    start, end = bounds(day.local_date, day.timezone_name)
    return bool(day.slots and day.slots[0].start == start and day.slots[-1].end == end
                and all(a.end == b.start for a, b in zip(day.slots, day.slots[1:])))


def days_from_slots(slots: tuple[TariffSlot, ...], timezone_name: str, source: str,
                    benchmark: float | None = None) -> list[TariffDay]:
    grouped = {}
    zone = ZoneInfo(timezone_name)
    for slot in slots:
        cursor = slot.start
        while cursor < slot.end:
            local_date = cursor.astimezone(zone).date()
            _, midnight = bounds(local_date, timezone_name)
            end = min(midnight, slot.end)
            grouped.setdefault(local_date, []).append(TariffSlot(cursor, end, slot.price))
            cursor = end
    return [TariffDay(key, timezone_name, tuple(value), source, benchmark)
            for key, value in sorted(grouped.items())]


def stats(slots: tuple[TariffSlot, ...]) -> dict:
    if not slots:
        return {}
    weights = [(s.end - s.start).total_seconds() for s in slots]
    total = sum(weights)
    mean = sum(s.price * w for s, w in zip(slots, weights)) / total
    variance = sum(w * (s.price - mean) ** 2 for s, w in zip(slots, weights)) / total
    ordered = sorted(zip((s.price for s in slots), weights))
    cumulative = 0
    median = ordered[-1][0]
    for price, weight in ordered:
        cumulative += weight
        if cumulative >= total / 2:
            median = price
            break
    low, high = min(s.price for s in slots), max(s.price for s in slots)
    return {"mean": round(mean, 6), "median": median, "min": low, "max": high,
            "range": high - low, "standard_deviation": round(math.sqrt(variance), 6),
            "negative_minutes": sum(w / 60 for s, w in zip(slots, weights) if s.price < 0)}


def cheapest_window(slots: tuple[TariffSlot, ...], hours: int, now: datetime) -> dict | None:
    duration = timedelta(hours=hours)
    candidates = []
    future = tuple(slot for slot in slots if slot.start >= now)
    if not future:
        return None
    starts = {slot.start for slot in future} | {
        slot.end - duration for slot in future if slot.end - duration >= future[0].start
    }
    for start in sorted(starts):
        end = start + duration
        cursor, cost = start, 0.0
        for slot in future:
            if slot.end <= cursor:
                continue
            if slot.start > cursor:
                break
            stop = min(slot.end, end)
            cost += slot.price * (stop - cursor).total_seconds() / 3600
            cursor = stop
            if cursor == end:
                candidates.append((cost, start, end))
                break
    if not candidates:
        return None
    cost, start, end = min(candidates)
    return {"start": start.isoformat(), "end": end.isoformat(),
            "average_price_p_per_kwh": round(cost / hours, 6),
            "cost_at_1kw_pence": round(cost, 6)}


def wall_prices(day: TariffDay) -> dict[str, float]:
    """Compare matching local half hours; average repeated DST hours per day."""
    result = {}
    zone = ZoneInfo(day.timezone_name)
    for slot in day.slots:
        cursor = slot.start
        while cursor < slot.end:
            key = cursor.astimezone(zone).strftime("%H:%M")
            result.setdefault(key, []).append(slot.price)
            cursor += timedelta(minutes=30)
    return {key: statistics.mean(values) for key, values in result.items()}


def analyse(slots: tuple[TariffSlot, ...], history: list[TariffDay], *, now: datetime,
            timezone_name: str, source: str) -> dict:
    now = utc(now)
    today = now.astimezone(ZoneInfo(timezone_name)).date()
    tomorrow = today + timedelta(days=1)
    live_days = days_from_slots(slots, timezone_name, source)
    target = next((day for day in live_days if day.local_date == tomorrow), None)
    past = sorted((day for day in history if today - timedelta(days=14) <= day.local_date < today and complete(day)),
                  key=lambda day: day.local_date)[-14:]
    result = {"status": "ready" if target and complete(target) else "limited" if slots else "waiting",
              "tomorrow_complete": bool(target and complete(target)),
              "history_days": len(past), "warmup_days_required": 14,
              "baseline_status": "ready" if len(past) >= 14 else "warming_up",
              "timezone": timezone_name, "updated_at": now.isoformat(),
              "windows": {str(hours): cheapest_window(slots, hours, now) for hours in range(1, 5)}}
    if not target or not complete(target):
        result.update(tomorrow_classification="waiting", summary="Waiting for complete next-day tariff rates.")
        return result
    summary = stats(target.slots)
    result["tomorrow_statistics"] = summary
    zone = ZoneInfo(timezone_name)
    bands = {}
    for name, start, end in (("overnight", 0, 7), ("morning", 7, 10), ("daytime", 10, 16), ("evening", 16, 19), ("late", 19, 24)):
        bands[name] = stats(tuple(s for s in target.slots if start <= s.start.astimezone(zone).hour < end)).get("mean")
    result["time_bands"] = bands
    result["evening_peak"] = "strong" if bands["evening"] is not None and bands["evening"] > summary["mean"] + summary["standard_deviation"] else "ordinary"
    result["volatility"] = "high" if summary["standard_deviation"] > 10 else "moderate" if summary["standard_deviation"] > 5 else "low"
    classification = "warming_up"
    if len(past) >= 14:
        averages = [stats(day.slots)["mean"] for day in past]
        percentile = 100 * (sum(value < summary["mean"] for value in averages)
                            + 0.5 * sum(value == summary["mean"] for value in averages)) / len(averages)
        classification = "cheap" if percentile <= 25 else "expensive" if percentile >= 75 else "typical"
        result["recent_percentile"] = round(percentile, 2)
        result["recent_average_p_per_kwh"] = statistics.mean(averages)
        historical = [wall_prices(day) for day in past]
        target_prices = wall_prices(target)
        baseline = {key: statistics.median([day[key] for day in historical if key in day]) for key in target_prices}
        result["matching_half_hour_baseline"] = baseline
        differences = [target_prices[key] - baseline[key] for key in target_prices]
        result["raw_baseline_difference_p_per_kwh"] = statistics.mean(differences)
        a, b = list(target_prices.values()), list(baseline.values())
        ma, mb = statistics.mean(a), statistics.mean(b)
        denom = math.sqrt(sum((v - ma) ** 2 for v in a) * sum((v - mb) ** 2 for v in b))
        similarity = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / denom if denom else None
        result["shape_similarity"] = similarity
        result["pattern"] = "unusual" if similarity is not None and similarity < 0.5 else "typical" if similarity is not None else "flat"
    result["tomorrow_classification"] = classification
    result["summary"] = (f"Tomorrow averages {summary['mean']:.2f} p/kWh; {classification.replace('_', ' ')}. "
                         f"Volatility: {result['volatility']}. Evening peak: {result['evening_peak']}.")
    return result
