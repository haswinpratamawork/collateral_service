"""Rumah123 source: discover listing URLs and parse listing pages.

Rumah123 is a Next.js App Router site. Listing data is not in a single ``__NEXT_DATA__``
blob; it lives in the streamed RSC payload (``self.__next_f.push([1, "..."])`` chunks).
We reconstruct that stream, then pull out the ``listing`` object — which carries the price,
location, and ``attrs`` (bedroom/bathroom/landSize/builtSize/certificate/...). The agent
name is taken from the page's JSON-LD ``Product`` offer (a stable, standardized field).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from typing import Any

from scraper.config import Config
from scraper.fetch.base import Fetcher, FetchError
from scraper.sources.base import Source

logger = logging.getLogger("scraper.sources.rumah123")

# Listing detail URLs end with a slug + short code + digits, e.g. ...-hos41544728/,
# ...-aps7274021/, ...-las9013631/ (and sponsored v* variants).
LISTING_URL_RE = re.compile(r"/properti/[a-z0-9\-]+/[a-z0-9\-]+-[a-z]{2,5}\d+/")

_RSC_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,(".*?")\]\)', re.S)
_LD_JSON_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
_LISTING_KEY_RE = re.compile(r'"listing":\{')


def _slugify(name: str | None) -> str | None:
    """'Tanah Abang' -> 'tanah-abang'; None/blank -> None."""
    if not name or not name.strip():
        return None
    return re.sub(r"\s+", "-", name.strip().lower())


def _reconstruct_rsc(html: str) -> str:
    """Concatenate and unescape the RSC string chunks into one stream."""
    return "".join(json.loads(chunk) for chunk in _RSC_CHUNK_RE.findall(html))


def _extract_balanced_object(text: str, start: int) -> str | None:
    """Return the JSON object substring starting at ``text[start] == '{'``.

    Brace-matches while respecting string literals and escapes.
    """
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _iter_jsonld(html: str) -> Iterator[Any]:
    for match in _LD_JSON_RE.finditer(html):
        try:
            yield json.loads(match.group(1))
        except json.JSONDecodeError:
            continue


def _find_product_ld(html: str) -> dict[str, Any] | None:
    """Return the Product/Residence JSON-LD object, if present."""
    for doc in _iter_jsonld(html):
        if isinstance(doc, dict):
            types = doc.get("@type")
            types = types if isinstance(types, list) else [types]
            if "Product" in types:
                return doc
    return None


def _find_listing_object(stream: str, prefer_id: str | None) -> dict[str, Any] | None:
    """Find the listing object in the RSC stream.

    Picks the one whose originId matches ``prefer_id`` when known, else the first object
    that has both ``originId`` and ``attrs`` (skips UI label dictionaries).
    """
    fallback: dict[str, Any] | None = None
    for match in _LISTING_KEY_RE.finditer(stream):
        raw = _extract_balanced_object(stream, match.end() - 1)
        if not raw or '"originId"' not in raw or '"attrs"' not in raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if prefer_id and obj.get("originId") == prefer_id:
            return obj
        if fallback is None:
            fallback = obj
    return fallback


class Rumah123Source(Source):
    name = "rumah123"

    def __init__(
        self,
        config: Config,
        fetcher: Fetcher,
        *,
        max_pages: int = 200,
        district: str | None = None,
    ) -> None:
        self._config = config
        self._fetcher = fetcher
        self._max_pages = max_pages
        self._district = district
        self.discovery_incomplete = False

    # --- discovery --------------------------------------------------------------

    def matches_scope(self, raw: dict[str, Any]) -> bool:
        """When scoped to a district, keep only listings whose district matches it.

        Drops promoted/out-of-area ads Rumah123 injects into every results page. A record
        with an unknown district is dropped (we cannot confirm it belongs).
        """
        if not self._district:
            return True
        return _slugify(raw.get("district")) == self._district

    def extract_listing_urls(self, html: str) -> list[str]:
        """Absolute listing-detail URLs found on an index page (deduped, in order)."""
        seen: dict[str, None] = {}
        for path in LISTING_URL_RE.findall(html):
            seen.setdefault(self._config.base_url + path, None)
        return list(seen)

    def discover(self) -> Iterator[str]:
        self.discovery_incomplete = False
        seen: set[str] = set()
        for city in self._config.cities:
            for property_type in self._config.property_types:
                yield from self._discover_combo(city, property_type, seen)

    def _discover_combo(
        self, city: str, property_type: str, seen: set[str]
    ) -> Iterator[str]:
        for page in range(1, self._max_pages + 1):
            url = self._config.index_url(city, property_type, page, district=self._district)
            try:
                html = self._fetcher.get(url)
            except FetchError as exc:
                # An index fetch failed (e.g. network/rate-limit). The crawl is now
                # partial — flag it so the orchestrator skips delisting.
                self.discovery_incomplete = True
                level = logging.WARNING if page == 1 else logging.INFO
                logger.log(
                    level,
                    "index fetch failed (%s %s p%d) — may be incomplete: %s",
                    self._district or city,
                    property_type,
                    page,
                    exc,
                )
                break
            urls = self.extract_listing_urls(html)
            if not urls:
                break  # no listings -> end of pages
            new = [u for u in urls if u not in seen]
            if not new:
                break  # same page repeating -> stop
            for u in new:
                seen.add(u)
                yield u
        else:
            # Loop ran every page without an early stop -> the cap was reached and there
            # may be more listings. Never truncate silently.
            logger.warning(
                "hit max_pages=%d for %s %s — results may be truncated; raise --max-pages",
                self._max_pages,
                self._district or city,
                property_type,
            )

    # --- parsing ----------------------------------------------------------------

    def parse(self, html: str) -> dict[str, Any]:
        product = _find_product_ld(html)
        sku = product.get("sku") if product else None

        stream = _reconstruct_rsc(html)
        listing = _find_listing_object(stream, prefer_id=sku)
        if listing is None:
            raise ValueError("no listing object found in page")

        attrs = listing.get("attrs") or {}
        common = attrs.get("common") or {}
        location = listing.get("location") or {}
        price = listing.get("price") or {}
        time = listing.get("time") or {}
        path = listing.get("url") or ""

        return {
            "listing_id": listing.get("originId") or sku,
            "source": self.name,
            "url": self._absolute(path),
            "title": listing.get("title"),
            "price_offer": price.get("offer"),
            "price_tag": price.get("tag"),
            "address_text": listing.get("address") or location.get("text"),
            "province": (location.get("province") or {}).get("name"),
            "city": (location.get("city") or {}).get("name"),
            "district": (location.get("district") or {}).get("name"),
            "latitude": location.get("latitude"),
            "longitude": location.get("longitude"),
            "listing_type_label": common.get("listingType"),
            "created_ts": time.get("created"),
            "updated_ts": time.get("updated"),
            "agent_name": self._agent_name(product),
            "attrs_common": common,
            "attrs_interior": attrs.get("interior") or {},
            "attrs_exterior": attrs.get("exterior") or {},
            "attrs_other": attrs.get("other") or {},
            "raw": listing,
        }

    def _absolute(self, path: str) -> str:
        if not path:
            return ""
        if path.startswith("http"):
            return path
        return self._config.base_url + path

    @staticmethod
    def _agent_name(product: dict[str, Any] | None) -> str | None:
        if not product:
            return None
        seller = (product.get("offers") or {}).get("seller") or {}
        name = seller.get("name")
        return name.strip() if isinstance(name, str) else None
