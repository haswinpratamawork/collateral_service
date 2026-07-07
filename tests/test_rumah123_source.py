"""Tests for scraper.sources.rumah123 (Phase 3). Parses saved fixtures — no live calls."""

from __future__ import annotations

from pathlib import Path

import pytest

from scraper.config import Config
from scraper.fetch.base import Fetcher, FetchError
from scraper.sources.rumah123 import LISTING_URL_RE, Rumah123Source

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def _source(fetcher: Fetcher | None = None, **cfg) -> Rumah123Source:
    return Rumah123Source(Config(**cfg), fetcher or _NullFetcher())


class _NullFetcher(Fetcher):
    def get(self, url: str) -> str:  # pragma: no cover - not used in parse tests
        raise AssertionError("fetch should not be called")


# --- discovery / URL extraction ---------------------------------------------------


def test_extract_listing_urls_from_index() -> None:
    urls = _source().extract_listing_urls(_read("rumah123_index_house.html"))
    assert len(urls) > 10
    assert len(urls) == len(set(urls))  # deduped
    assert all(u.startswith("https://www.rumah123.com/properti/") for u in urls)
    assert all(LISTING_URL_RE.search(u) for u in urls)


def test_discover_paginates_until_empty() -> None:
    index_html = _read("rumah123_index_house.html")

    class _PagedFetcher(Fetcher):
        def __init__(self) -> None:
            self.requested: list[str] = []

        def get(self, url: str) -> str:
            self.requested.append(url)
            # page 1 returns listings; any later page is empty -> stop
            return index_html if ("page=" not in url) else "<html>no listings</html>"

    fetcher = _PagedFetcher()
    source = Rumah123Source(
        Config(cities=("jakarta-selatan",), property_types=("rumah",)), fetcher
    )
    urls = list(source.discover())

    assert urls  # got the page-1 listings
    assert urls == list(dict.fromkeys(urls))  # globally deduped
    # fetched page 1 then page 2 (empty) and stopped
    assert any("page=2" in u for u in fetcher.requested)
    assert not any("page=3" in u for u in fetcher.requested)


def test_discover_stops_on_fetch_error() -> None:
    class _ErrorFetcher(Fetcher):
        def get(self, url: str) -> str:
            raise FetchError("404")

    source = Rumah123Source(
        Config(cities=("bekasi",), property_types=("rumah",)), _ErrorFetcher()
    )
    assert list(source.discover()) == []


# --- parsing ----------------------------------------------------------------------


def test_parse_house() -> None:
    rec = _source().parse(_read("rumah123_listing_house.html"))
    assert rec["listing_id"] == "hos41544728"
    assert rec["source"] == "rumah123"
    assert rec["price_offer"] == 3_870_000_000
    assert rec["title"].startswith("Rumah Siap Huni")
    assert rec["province"] == "DKI Jakarta"
    assert rec["city"] == "Jakarta Selatan"
    assert rec["district"] == "Jagakarsa"
    assert rec["listing_type_label"] == "Rumah"
    assert rec["attrs_common"]["bedroom"] == "6"
    assert rec["attrs_common"]["bathroom"] == "4"
    assert rec["attrs_common"]["landSize"] == "136 m²"
    assert rec["attrs_common"]["builtSize"] == "230 m²"
    assert rec["attrs_common"]["certificate"] == "SHM"
    assert rec["agent_name"]  # from JSON-LD seller
    assert rec["url"].endswith("/")
    assert isinstance(rec["created_ts"], int)  # Rumah123 "dibuat" epoch
    assert isinstance(rec["updated_ts"], int)  # Rumah123 "diperbarui" epoch


def test_parse_apartment_has_no_land_size() -> None:
    rec = _source().parse(_read("rumah123_listing_apartment.html"))
    assert rec["listing_id"].startswith("aps")
    assert rec["listing_type_label"] == "Apartemen"
    assert rec["attrs_common"]["bedroom"] == "3"
    assert rec["attrs_common"]["landSize"] == ""  # apartments have no land
    assert rec["attrs_common"]["builtSize"] == "88 m²"
    assert rec["attrs_common"]["certificate"] == "PPJB"
    assert rec["price_offer"] > 0


def test_parse_land_has_no_bedrooms() -> None:
    rec = _source().parse(_read("rumah123_listing_land.html"))
    assert rec["listing_id"].startswith("las")
    assert rec["listing_type_label"] == "Tanah"
    assert rec["attrs_common"]["bedroom"] == ""  # land has no rooms
    assert rec["attrs_common"]["bathroom"] == ""
    assert rec["attrs_common"]["landSize"] == "519 m²"
    assert rec["attrs_common"]["certificate"] == "HGB"


def test_parse_raises_when_no_listing() -> None:
    with pytest.raises(ValueError):
        _source().parse("<html><body>nothing here</body></html>")


def test_matches_scope_filters_other_districts() -> None:
    scoped = Rumah123Source(Config(), _NullFetcher(), district="jagakarsa")
    assert scoped.matches_scope({"district": "Jagakarsa"}) is True
    assert scoped.matches_scope({"district": "Alam Sutera"}) is False  # promoted ad
    assert scoped.matches_scope({"district": None}) is False           # unknown -> drop

    # multi-word district slugifies correctly
    tanah_abang = Rumah123Source(Config(), _NullFetcher(), district="tanah-abang")
    assert tanah_abang.matches_scope({"district": "Tanah Abang"}) is True

    # without a district, nothing is filtered
    assert _source().matches_scope({"district": "Anywhere"}) is True
