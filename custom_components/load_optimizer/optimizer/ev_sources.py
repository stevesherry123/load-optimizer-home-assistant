"""Combine explicitly configured EV tariff sources without inventing coverage."""

from .tariffs import normalize_tariff_periods, tariff_periods_from_entity


def ev_tariff_periods(sources: list[dict | None], **kwargs) -> tuple[list[dict], list[str]]:
    """Use published slots from available sources; retain missing-source detail.

    Tomorrow's empty event is normal before publication. It must not erase
    today's usable slots, nor create a price for tomorrow. Conflicting published
    intervals are an error, regardless of source order.
    """
    periods = []
    issues = []
    for index, entity in enumerate(sources):
        if not entity or str(entity.get("state", "")).lower() in {"", "unknown", "unavailable", "none"}:
            issues.append(f"Source {index + 1}: unavailable")
            continue
        try:
            periods.extend(tariff_periods_from_entity(entity, **kwargs))
        except (TypeError, ValueError) as error:
            issues.append(f"Source {index + 1}: {error}")
    periods = normalize_tariff_periods(periods)
    periods = [period for period in periods if period["end"] > kwargs["reference_utc"]]
    if not periods:
        raise ValueError("No configured EV tariff source contains future prices")
    return periods, issues
