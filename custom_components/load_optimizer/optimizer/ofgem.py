"""Parse Ofgem's effective-dated regional electricity price-cap tables."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import calendar
import json
import re
from typing import Any

OFGEM_PRICE_CAP_URL = (
    "https://www.ofgem.gov.uk/your-energy-supply/your-energy-bill/"
    "energy-price-cap-unit-rates-and-standing-charges"
)
EVERVIZ_EMBED = re.compile(
    r'https://app\.everviz\.com/inject/(?P<project>[A-Za-z0-9_-]+)/?[^"\s<]*'
)
UNIT_RATE_HEADER = re.compile(
    r"^Unit rate\s+(?P<start>[A-Za-z]+)\s+to\s+(?P<end>[A-Za-z]+)\s+"
    r"(?P<year>\d{4})$",
    re.IGNORECASE,
)
NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)")
PAYMENT_TITLES = {
    "direct_debit": "paid by Direct Debit, single rate",
    "standard_credit": "paid by standard credit, single rate",
    "prepayment": "paid by prepayment meter, single rate",
}


@dataclass(frozen=True)
class PriceCapReference:
    """One regional electricity unit-rate benchmark."""

    effective_from: date
    effective_to: date
    unit_rate_p_per_kwh: float
    region: str
    payment_method: str
    source: str = "ofgem"

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["effective_from"] = self.effective_from.isoformat()
        value["effective_to"] = self.effective_to.isoformat()
        return value


def everviz_urls(page_html: str) -> list[str]:
    """Return each unique Everviz embed URL linked by the Ofgem page."""
    projects = dict.fromkeys(match.group("project") for match in EVERVIZ_EMBED.finditer(page_html))
    return [f"https://app.everviz.com/inject/{project}/" for project in projects]


def _table_options(source: str) -> dict[str, Any]:
    marker = "var options = "
    start = source.find(marker)
    if start < 0:
        raise ValueError("Everviz table contains no options payload")
    payload = source[start + len(marker) :].lstrip()
    options, _ = json.JSONDecoder().raw_decode(payload)
    return options


def _plain_text(value: object) -> str:
    return re.sub(r"<[^>]+>", " ", str(value)).replace("&amp;", "&").strip()


def _period(header: str) -> tuple[date, date]:
    match = UNIT_RATE_HEADER.match(" ".join(header.split()))
    if not match:
        raise ValueError(f"Unsupported Ofgem unit-rate period: {header}")
    start_month = list(calendar.month_name).index(match.group("start").title())
    end_month = list(calendar.month_name).index(match.group("end").title())
    year = int(match.group("year"))
    start = date(year, start_month, 1)
    end_year = year + (1 if end_month == 12 else 0)
    end_month_next = 1 if end_month == 12 else end_month + 1
    return start, date(end_year, end_month_next, 1)


def _price(value: object) -> float:
    match = NUMBER.search(str(value))
    if not match:
        raise ValueError(f"Ofgem unit rate is not numeric: {value}")
    price = float(match.group())
    if not 0 < price < 200:
        raise ValueError(f"Ofgem unit rate is outside the expected range: {price}")
    return price


def parse_everviz_references(
    source: str,
    *,
    region: str,
    payment_method: str,
) -> list[PriceCapReference]:
    """Parse matching regional single-rate electricity references from a table."""
    expected_title = PAYMENT_TITLES.get(payment_method)
    if expected_title is None:
        raise ValueError(f"Unsupported price-cap payment method: {payment_method}")
    options = _table_options(source)
    title = _plain_text(options.get("options", {}).get("title", {}).get("text", ""))
    if "Electricity" not in title or expected_title.lower() not in title.lower():
        return []

    rows = options.get("data", {}).get("value")
    if not isinstance(rows, list) or len(rows) < 2:
        raise ValueError("Ofgem table has no regional data")
    headers = [str(value) for value in rows[0]]
    selected = next(
        (row for row in rows[1:] if row and str(row[0]).strip() == region),
        None,
    )
    if selected is None:
        raise ValueError(f"Ofgem table has no row for region: {region}")

    references = []
    for index, header in enumerate(headers):
        if not header.lower().startswith("unit rate"):
            continue
        effective_from, effective_to = _period(header)
        references.append(
            PriceCapReference(
                effective_from=effective_from,
                effective_to=effective_to,
                unit_rate_p_per_kwh=_price(selected[index]),
                region=region,
                payment_method=payment_method,
            )
        )
    if not references:
        raise ValueError("Ofgem table contains no unit-rate columns")
    return sorted(references, key=lambda reference: reference.effective_from)


def reference_for_date(
    references: list[PriceCapReference], reference_date: date
) -> PriceCapReference | None:
    """Return the reference whose effective period contains the supplied date."""
    return next(
        (
            reference
            for reference in references
            if reference.effective_from <= reference_date < reference.effective_to
        ),
        None,
    )

