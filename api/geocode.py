"""Reverse geocoding: latitude/longitude -> kelurahan + postal code (kode pos).

Uses the Google Maps Geocoding API. In Indonesia, Google exposes the kelurahan as
``administrative_area_level_4`` (sometimes ``sublocality_level_1``/``sublocality``), and the
postal code as ``postal_code``.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# Component types that represent a kelurahan in Indonesian Google results, most-specific first.
_KELURAHAN_TYPES = ("administrative_area_level_4", "sublocality_level_1", "sublocality")


@dataclass
class GeoResult:
    kelurahan: str | None = None
    kode_pos: str | None = None


class GoogleGeocoder:
    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=15.0)

    def reverse(self, latitude: float, longitude: float) -> GeoResult:
        """Reverse-geocode coordinates. Returns empty fields on any failure."""
        try:
            resp = self._client.get(
                GEOCODE_URL,
                params={
                    "latlng": f"{latitude},{longitude}",
                    "key": self._api_key,
                    "language": "id",
                },
            )
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return GeoResult()
        if data.get("status") != "OK":
            return GeoResult()
        return _extract(data.get("results", []))

    def close(self) -> None:
        self._client.close()


def _extract(results: list[dict]) -> GeoResult:
    """Pull kelurahan + postal code from Google geocode results (most specific wins)."""
    kelurahan: str | None = None
    kode_pos: str | None = None
    for result in results:
        for component in result.get("address_components", []):
            types = component.get("types", [])
            if kode_pos is None and "postal_code" in types:
                kode_pos = component.get("long_name")
            if kelurahan is None and any(t in types for t in _KELURAHAN_TYPES):
                kelurahan = component.get("long_name")
        if kelurahan and kode_pos:
            break
    return GeoResult(kelurahan=kelurahan, kode_pos=kode_pos)
