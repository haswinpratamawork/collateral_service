"""Tests for the api/ service. No live HTTP — fixtures + a fake geocoder."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from api.geocode import GeoResult, GoogleGeocoder, _extract
from api.service import ListingService
from scraper.config import Config
from scraper.fetch.base import Fetcher

FIXTURES = Path(__file__).parent / "fixtures"

_GOOGLE_OK = {
    "status": "OK",
    "results": [
        {
            "address_components": [
                {"long_name": "Senen", "types": ["administrative_area_level_4", "political"]},
                {"long_name": "Jakarta Pusat", "types": ["administrative_area_level_2"]},
                {"long_name": "10410", "types": ["postal_code"]},
            ]
        }
    ],
}


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


class FakeFetcher(Fetcher):
    def __init__(self, html: str) -> None:
        self._html = html

    def get(self, url: str) -> str:
        return self._html


class FakeGeocoder:
    def __init__(self, result: GeoResult) -> None:
        self.result = result
        self.calls: list[tuple[float, float]] = []

    def reverse(self, latitude: float, longitude: float) -> GeoResult:
        self.calls.append((latitude, longitude))
        return self.result


def _service(html: str, geocoder) -> ListingService:
    cfg = Config(request_delay_min=0.0, request_delay_max=0.0)
    return ListingService(geocoder, fetcher=FakeFetcher(html), config=cfg)


# --- geocoder -------------------------------------------------------------------


def test_geocode_extract_picks_kelurahan_and_postcode():
    geo = _extract(_GOOGLE_OK["results"])
    assert geo.kelurahan == "Senen"
    assert geo.kode_pos == "10410"


def _client(payload: dict) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)))


def test_geocoder_reverse_mocked():
    geo = GoogleGeocoder("key", client=_client(_GOOGLE_OK)).reverse(-6.18, 106.84)
    assert (geo.kelurahan, geo.kode_pos) == ("Senen", "10410")


def test_geocoder_handles_zero_results():
    geo = GoogleGeocoder("key", client=_client({"status": "ZERO_RESULTS"})).reverse(0, 0)
    assert geo.kelurahan is None and geo.kode_pos is None


# --- service --------------------------------------------------------------------


def test_service_extracts_and_geocodes_valid_coords():
    geo = FakeGeocoder(GeoResult(kelurahan="Senen", kode_pos="10410"))
    result = _service(_read("rumah123_listing_with_coords.html"), geo).extract(
        "https://www.rumah123.com/properti/jakarta-pusat/hos41138420/"
    )
    assert result.luas_tanah == 294.0
    assert result.luas_bangunan == 482.0
    assert result.kelurahan == "Senen"
    assert result.kode_pos == "10410"
    assert len(geo.calls) == 1
    lat, lon = geo.calls[0]
    assert round(lat, 3) == -6.188 and round(lon, 3) == 106.843


def test_service_skips_geocode_when_coords_obfuscated():
    # The house fixture has lat == lon (obfuscated) -> normalize drops the coords.
    geo = FakeGeocoder(GeoResult(kelurahan="X", kode_pos="Y"))
    result = _service(_read("rumah123_listing_house.html"), geo).extract(
        "https://www.rumah123.com/properti/x/hos41544728/"
    )
    assert result.luas_tanah == 136.0
    assert result.luas_bangunan == 230.0
    assert result.kode_pos is None and result.kelurahan is None
    assert geo.calls == []  # never geocode without real coordinates


# --- FastAPI endpoint -----------------------------------------------------------

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from api.main import app, get_service  # noqa: E402


def test_endpoint_returns_the_four_fields():
    geo = FakeGeocoder(GeoResult(kelurahan="Senen", kode_pos="10410"))
    svc = _service(_read("rumah123_listing_with_coords.html"), geo)
    app.dependency_overrides[get_service] = lambda: svc
    try:
        resp = TestClient(app).get(
            "/extract",
            params={"url": "https://www.rumah123.com/properti/jakarta-pusat/hos41138420/"},
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "luas_tanah": 294.0,
            "luas_bangunan": 482.0,
            "kode_pos": "10410",
            "kelurahan": "Senen",
        }
    finally:
        app.dependency_overrides.clear()


def test_endpoint_rejects_non_rumah123_url():
    app.dependency_overrides[get_service] = lambda: object()  # never reached
    try:
        resp = TestClient(app).get("/extract", params={"url": "https://example.com/foo"})
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()
