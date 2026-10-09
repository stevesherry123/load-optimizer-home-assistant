"""Daily cached Ofgem price-cap lookup."""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timezone
import logging
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .optimizer.ofgem import (
    OFGEM_PRICE_CAP_URL,
    PriceCapReference,
    everviz_urls,
    parse_everviz_references,
    reference_for_date,
)

LOGGER = logging.getLogger(__name__)
STORE_VERSION = 1
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_TABLES = 16
TRUSTED_SOURCE_HOSTS = {"www.ofgem.gov.uk", "ofgem.gov.uk", "app.everviz.com"}
REQUEST_HEADERS = {
    "User-Agent": "Load-Optimizer-Home-Assistant/1.5 (+https://github.com/stevesherry123/load-optimizer-home-assistant)"
}


class PriceCapManager:
    """Fetch and retain validated effective-dated Ofgem references."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.store = Store(hass, STORE_VERSION, f"{DOMAIN}.price_cap.{entry.entry_id}")
        self.cache: dict = {}
        self.loaded = False

    async def _async_load(self) -> None:
        if self.loaded:
            return
        stored = await self.store.async_load()
        self.cache = stored if isinstance(stored, dict) else {}
        self.loaded = True

    @staticmethod
    def _references(values: list[dict]) -> list[PriceCapReference]:
        references = []
        for value in values:
            try:
                references.append(
                    PriceCapReference(
                        effective_from=datetime.fromisoformat(value["effective_from"]).date(),
                        effective_to=datetime.fromisoformat(value["effective_to"]).date(),
                        unit_rate_p_per_kwh=float(value["unit_rate_p_per_kwh"]),
                        region=str(value["region"]),
                        payment_method=str(value["payment_method"]),
                        source=str(value.get("source", "ofgem")),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return references

    async def _async_fetch(
        self, region: str, payment_method: str
    ) -> list[PriceCapReference]:
        session = async_get_clientsession(self.hass)
        page = await self._async_fetch_text(session, OFGEM_PRICE_CAP_URL)
        urls = everviz_urls(page)
        if not urls:
            raise ValueError("Ofgem page contains no price-cap tables")
        if len(urls) > MAX_TABLES:
            raise ValueError("Ofgem page contains too many price-cap tables")
        for url in urls:
            source = await self._async_fetch_text(session, url)
            references = parse_everviz_references(
                source,
                region=region,
                payment_method=payment_method,
            )
            if references:
                return references
        raise ValueError("Ofgem page contains no matching electricity table")

    @staticmethod
    async def _async_fetch_text(session, url: str) -> str:
        """Constrain redirects and decompressed response size at the HTTP boundary."""
        for _ in range(4):
            parsed = urlsplit(url)
            if (parsed.scheme != "https" or parsed.hostname not in TRUSTED_SOURCE_HOSTS
                    or parsed.username or parsed.password or parsed.port not in (None, 443)):
                raise ValueError("Price-cap source URL is not permitted")
            async with session.get(url, headers=REQUEST_HEADERS, timeout=30, allow_redirects=False) as response:
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    if not location:
                        raise ValueError("Price-cap source redirect has no destination")
                    url = urljoin(url, location)
                    continue
                response.raise_for_status()
                if response.status != 200:
                    raise ValueError("Price-cap source did not return a document")
                body = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise ValueError("Price-cap source exceeds the response size limit")
                return body.decode(response.charset or "utf-8")
        raise ValueError("Price-cap source redirected too many times")

    async def async_status(
        self,
        *,
        region: str | None,
        payment_method: str | None,
        timezone_name: str,
        now_utc: datetime | None = None,
    ) -> dict:
        """Return a current reference, refreshing the official source daily."""
        await self._async_load()
        if not region or not payment_method:
            return {"status": "not_configured", "source": "ofgem"}
        now_utc = now_utc or datetime.now(timezone.utc)
        local_date = now_utc.astimezone(ZoneInfo(timezone_name)).date()
        retrieved_at = self.cache.get("retrieved_at")
        cache_matches = (
            self.cache.get("region") == region
            and self.cache.get("payment_method") == payment_method
        )
        retrieved_today = False
        if retrieved_at and cache_matches:
            try:
                retrieved_today = (
                    datetime.fromisoformat(retrieved_at)
                    .astimezone(ZoneInfo(timezone_name))
                    .date()
                    == local_date
                )
            except ValueError:
                pass

        fetch_error = None
        if not retrieved_today:
            try:
                async with asyncio.timeout(60):
                    references = await self._async_fetch(region, payment_method)
                retrieved_at = now_utc.isoformat()
                self.cache = {
                    "region": region,
                    "payment_method": payment_method,
                    "retrieved_at": retrieved_at,
                    "source_url": OFGEM_PRICE_CAP_URL,
                    "references": [reference.as_dict() for reference in references],
                }
                await self.store.async_save(self.cache)
                cache_matches = True
            except Exception as error:  # Retain the last validated official value.
                fetch_error = type(error).__name__
                LOGGER.warning("Unable to refresh Ofgem price-cap reference (%s)", fetch_error)

        references = self._references(self.cache.get("references", [])) if cache_matches else []
        current = reference_for_date(references, local_date)
        if current is None:
            return {
                "status": "error" if fetch_error else "unavailable",
                "source": "ofgem",
                "region": region,
                "payment_method": payment_method,
                "error": fetch_error,
            }
        local_timezone = ZoneInfo(timezone_name)
        public_references = []
        for reference in references:
            value = reference.as_dict()
            value["effective_from_utc"] = datetime.combine(
                reference.effective_from,
                time.min,
                tzinfo=local_timezone,
            ).astimezone(timezone.utc).isoformat()
            value["effective_to_utc"] = datetime.combine(
                reference.effective_to,
                time.min,
                tzinfo=local_timezone,
            ).astimezone(timezone.utc).isoformat()
            public_references.append(value)
        return {
            "status": "stale" if fetch_error else "ready",
            "unit_rate_p_per_kwh": current.unit_rate_p_per_kwh,
            "effective_from": current.effective_from.isoformat(),
            "effective_to": current.effective_to.isoformat(),
            "region": region,
            "payment_method": payment_method,
            "source": "ofgem",
            "source_url": self.cache.get("source_url", OFGEM_PRICE_CAP_URL),
            "retrieved_at": retrieved_at,
            "stale": fetch_error is not None,
            "error": fetch_error,
            "references": public_references,
        }
