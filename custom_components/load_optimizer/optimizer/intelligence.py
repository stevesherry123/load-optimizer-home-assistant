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


def forecast_coverage(day: TariffDay | None, local_date: date, timezone_name: str) -> dict:
    """Separate a usable published prefix from a complete historical day."""
    start, end = bounds(local_date, timezone_name)
    slots = day.slots if day else ()
    gap = any(a.end != b.start for a, b in zip(slots, slots[1:]))
    prefix = bool(slots and slots[0].start == start and not gap)
    required_end = datetime.combine(local_date, time(19), ZoneInfo(timezone_name)).astimezone(timezone.utc)
    full = bool(day and complete(day))
    usable = bool(prefix and slots[-1].end >= required_end)
    status = ("missing" if not slots else "gapped" if gap else "full_day" if full
              else "partial_day" if usable else "insufficient")
    return {"date": local_date.isoformat(), "status": status, "usable": usable,
            "complete": full, "start": slots[0].start.isoformat() if slots else None,
            "end": slots[-1].end.isoformat() if slots else None,
            "expected_start": start.isoformat(), "expected_end": end.isoformat(),
            "known_minutes": sum((s.end - s.start).total_seconds() / 60 for s in slots),
            "expected_minutes": (end - start).total_seconds() / 60,
            "trailing_missing_minutes": (end - slots[-1].end).total_seconds() / 60 if slots else None,
            "starts_at_midnight": bool(slots and slots[0].start == start),
            "has_internal_gap": gap}


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
    for index, (price, weight) in enumerate(ordered):
        cumulative += weight
        if cumulative >= total / 2:
            median = (price + ordered[index + 1][0]) / 2 if cumulative == total / 2 and index + 1 < len(ordered) else price
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


def wall_intervals(day: TariffDay) -> list[tuple[float, float, float]]:
    """Split UTC durations into wall-time half hours, retaining DST repeats."""
    result = []
    zone = ZoneInfo(day.timezone_name)
    for slot in day.slots:
        cursor = slot.start
        while cursor < slot.end:
            local = cursor.astimezone(zone)
            wall = local.hour * 3600 + local.minute * 60 + local.second + local.microsecond / 1_000_000
            stop = min(slot.end, cursor + timedelta(seconds=1800 - wall % 1800))
            result.append((wall, wall + (stop - cursor).total_seconds(), slot.price))
            cursor = stop
    return result


def wall_key(seconds: float) -> str:
    half_hour = int(seconds // 1800)
    return f"{half_hour // 2:02d}:{half_hour % 2 * 30:02d}"


def wall_prices(day: TariffDay) -> dict[str, float]:
    """Duration-weighted half hours; repeated wall times count once per day."""
    totals, weights = {}, {}
    for start, end, price in wall_intervals(day):
        key = wall_key(start)
        totals[key] = totals.get(key, 0) + price * (end - start)
        weights[key] = weights.get(key, 0) + end - start
    return {key: value / weights[key] for key, value in totals.items()}


def matching_reference(day: TariffDay, target: TariffDay) -> tuple[float, dict] | None:
    """Integrate history over exactly the target's wall intervals and weights."""
    historical = wall_intervals(day)
    totals, weights = {}, {}
    for start, end, _ in wall_intervals(target):
        overlapping = [(a, b, price) for a, b, price in historical if a < end and b > start]
        edges = sorted({start, end} | {max(start, a) for a, _, _ in overlapping}
                       | {min(end, b) for _, b, _ in overlapping})
        key = wall_key(start)
        for left, right in zip(edges, edges[1:]):
            prices = [price for a, b, price in overlapping if a <= left and b >= right]
            if not prices:
                return None
            totals[key] = totals.get(key, 0) + statistics.mean(prices) * (right - left)
            weights[key] = weights.get(key, 0) + right - left
    if not weights:
        return None
    return (round(sum(totals.values()) / sum(weights.values()), 6),
            {key: value / weights[key] for key, value in totals.items()})


def time_bands(day: TariffDay) -> tuple[dict, dict]:
    means, coverage = {}, {}
    zone = ZoneInfo(day.timezone_name)
    for name, first, last in (("overnight", 0, 7), ("morning", 7, 10), ("daytime", 10, 16),
                              ("evening", 16, 19), ("late", 19, 24)):
        start = datetime.combine(day.local_date, time(first), zone).astimezone(timezone.utc)
        end = (bounds(day.local_date, day.timezone_name)[1] if last == 24 else
               datetime.combine(day.local_date, time(last), zone).astimezone(timezone.utc))
        clipped = tuple(TariffSlot(max(s.start, start), min(s.end, end), s.price)
                        for s in day.slots if s.start < end and s.end > start)
        means[name] = stats(clipped).get("mean")
        full = bool(clipped and clipped[0].start == start and clipped[-1].end == end
                    and all(a.end == b.start for a, b in zip(clipped, clipped[1:])))
        coverage[name] = "complete" if full else "partial" if clipped else "unavailable"
    return means, coverage


def analyse(slots: tuple[TariffSlot, ...], history: list[TariffDay], *, now: datetime,
            timezone_name: str, source: str) -> dict:
    now = utc(now)
    today = now.astimezone(ZoneInfo(timezone_name)).date()
    tomorrow = today + timedelta(days=1)
    live_days = days_from_slots(slots, timezone_name, source)
    target = next((day for day in live_days if day.local_date == tomorrow), None)
    coverage = forecast_coverage(target, tomorrow, timezone_name)
    past = sorted((day for day in history if today - timedelta(days=14) <= day.local_date < today
                   and day.source == source and day.timezone_name == timezone_name and complete(day)),
                  key=lambda day: day.local_date)[-14:]
    result = {"status": "ready" if coverage["usable"] else "limited" if slots else "waiting",
              "tomorrow_complete": coverage["complete"], "tomorrow_date": tomorrow.isoformat(),
              "forecast_usable": coverage["usable"], "forecast_coverage": coverage,
              "forecast_fingerprint": target.fingerprint if target else None,
              "analysis_scope": "full_day" if coverage["complete"] else "published_hours",
              "window_scope": "known_future_prices",
              "history_days": len(past), "warmup_days_required": 14,
              "baseline_status": "ready" if len(past) >= 14 else "warming_up",
              "timezone": timezone_name, "updated_at": now.isoformat(),
              "windows": {str(hours): cheapest_window(slots, hours, now) for hours in range(1, 5)}}
    if not target or not coverage["usable"]:
        reason = ("Next-day tariff prices contain a gap." if coverage["has_internal_gap"] else
                  "Waiting for usable next-day tariff coverage through the evening peak.")
        result.update(tomorrow_classification="waiting", summary=reason)
        return result
    summary = stats(target.slots)
    result["tomorrow_statistics"] = summary
    bands, band_coverage = time_bands(target)
    result["time_bands"] = bands
    result["time_band_coverage"] = band_coverage
    result["evening_peak"] = "strong" if bands["evening"] is not None and bands["evening"] > summary["mean"] + summary["standard_deviation"] else "ordinary"
    result["volatility"] = "high" if summary["standard_deviation"] > 10 else "moderate" if summary["standard_deviation"] > 5 else "low"
    classification = "warming_up"
    references = [reference for day in past if (reference := matching_reference(day, target)) is not None]
    result["comparison_days"] = len(references)
    result["baseline_status"] = "ready" if len(references) >= 14 else "warming_up"
    if len(references) >= 14:
        averages = [mean for mean, _ in references]
        percentile = 100 * (sum(value < summary["mean"] for value in averages)
                            + 0.5 * sum(value == summary["mean"] for value in averages)) / len(averages)
        classification = "cheap" if percentile <= 25 else "expensive" if percentile >= 75 else "typical"
        result["recent_percentile"] = round(percentile, 2)
        result["recent_average_p_per_kwh"] = statistics.mean(averages)
        historical = [prices for _, prices in references]
        target_prices = wall_prices(target)
        baseline = {key: statistics.median([day[key] for day in historical if key in day]) for key in target_prices}
        result["matching_half_hour_baseline"] = baseline
        weights = {}
        for start, end, _ in wall_intervals(target):
            key = wall_key(start)
            weights[key] = weights.get(key, 0) + end - start
        result["raw_baseline_difference_p_per_kwh"] = sum(
            (target_prices[key] - baseline[key]) * weights[key] for key in target_prices) / sum(weights.values())
        a, b = list(target_prices.values()), list(baseline.values())
        ma, mb = statistics.mean(a), statistics.mean(b)
        denom = math.sqrt(sum((v - ma) ** 2 for v in a) * sum((v - mb) ** 2 for v in b))
        similarity = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / denom if denom else None
        result["shape_similarity"] = similarity
        result["pattern"] = "unusual" if similarity is not None and similarity < 0.5 else "typical" if similarity is not None else "flat"
    result["tomorrow_classification"] = classification
    zone = ZoneInfo(timezone_name)
    scope = ("Tomorrow" if coverage["complete"] else
             f"Published tomorrow prices ({target.slots[0].start.astimezone(zone):%H:%M}-"
             f"{target.slots[-1].end.astimezone(zone):%H:%M}, {timezone_name})")
    verb = "averages" if coverage["complete"] else "average"
    result["summary"] = (f"{scope} {verb} {summary['mean']:.2f} p/kWh; {classification.replace('_', ' ')}. "
                         f"Volatility: {result['volatility']}. Evening peak: {result['evening_peak']}.")
    if not coverage["complete"]:
        result["summary"] += " The remaining prices are not yet published."
    return result
