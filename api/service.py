"""Service: a Rumah123 listing URL -> LT/LB (from the page) + kode pos/kelurahan (geocoded).

Reuses the existing scraper (fetch + parse + normalize) for land/building area and the
coordinates, then reverse-geocodes the coordinates for postal code and kelurahan. Listings
with obfuscated/missing coordinates (lat == lon) get null kode_pos/kelurahan — we never guess.
"""

from __future__ import annotations

from dataclasses import replace

from api.geocode import GoogleGeocoder
from api.models import ExtractResult
from scraper.config import Config
from scraper.fetch.base import Fetcher
from scraper.fetch.httpx_fetcher import HttpxFetcher
from scraper.normalize import normalize
from scraper.sources.rumah123 import Rumah123Source


class ListingService:
    def __init__(
        self,
        geocoder: GoogleGeocoder,
        fetcher: Fetcher | None = None,
        config: Config | None = None,
    ) -> None:
        # No inter-request throttle: the API fetches a single user-provided URL on demand.
        self._config = config or replace(
            Config.from_env(), request_delay_min=0.0, request_delay_max=0.0
        )
        self._fetcher = fetcher or HttpxFetcher(self._config)
        self._source = Rumah123Source(self._config, self._fetcher)
        self._geocoder = geocoder

    def extract(self, url: str) -> ExtractResult:
        """Fetch + parse the listing, then geocode its coordinates. Raises on fetch/parse
        failure (handled by the API layer)."""
        record = normalize(self._source.parse(self._fetcher.get(url)))
        result = ExtractResult(
            luas_tanah=record.land_area_m2,
            luas_bangunan=record.building_area_m2,
        )
        if record.latitude is not None and record.longitude is not None:
            geo = self._geocoder.reverse(record.latitude, record.longitude)
            result.kode_pos = geo.kode_pos
            result.kelurahan = geo.kelurahan
        return result
