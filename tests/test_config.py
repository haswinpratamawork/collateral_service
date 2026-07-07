"""Tests for scraper.config (Phase 0.3)."""

from __future__ import annotations

import dataclasses

import pytest

from scraper.config import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_RETRIES,
    JABODETABEK_CITIES,
    Config,
)

# Env vars the config reads — cleared before each test for isolation.
_ENV_VARS = [
    "DATABASE_URL",
    "USER_AGENT",
    "REQUEST_DELAY_MIN",
    "REQUEST_DELAY_MAX",
    "MAX_CONCURRENCY",
    "MAX_RETRIES",
    "BASE_URL",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults_load_when_env_absent() -> None:
    cfg = Config.from_env()
    assert cfg.database_url == ""
    assert cfg.base_url == DEFAULT_BASE_URL
    assert cfg.max_retries == DEFAULT_MAX_RETRIES
    assert cfg.cities == JABODETABEK_CITIES
    assert "rumah" in cfg.property_types


def test_env_overrides_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/test_db")
    monkeypatch.setenv("REQUEST_DELAY_MIN", "1.5")
    monkeypatch.setenv("MAX_CONCURRENCY", "8")
    monkeypatch.setenv("MAX_RETRIES", "2")

    cfg = Config.from_env()

    assert cfg.database_url == "postgresql://localhost:5432/test_db"
    assert cfg.request_delay_min == 1.5
    assert cfg.max_concurrency == 8
    assert cfg.max_retries == 2


def test_normalized_property_type() -> None:
    assert Config.normalized_property_type("rumah") == "house"
    assert Config.normalized_property_type("apartemen") == "apartment"
    assert Config.normalized_property_type("tanah") == "land"
    assert Config.normalized_property_type("gudang") == "warehouse"
    assert Config.normalized_property_type("villa") == "other"


def test_index_url_format() -> None:
    cfg = Config.from_env()
    assert cfg.index_url("bekasi", "rumah") == f"{DEFAULT_BASE_URL}/jual/bekasi/rumah/"
    assert (
        cfg.index_url("bekasi", "rumah", page=3)
        == f"{DEFAULT_BASE_URL}/jual/bekasi/rumah/?page=3"
    )
    # page <= 1 has no query string
    assert cfg.index_url("depok", "tanah", page=1) == f"{DEFAULT_BASE_URL}/jual/depok/tanah/"


def test_index_url_with_district() -> None:
    cfg = Config.from_env()
    assert (
        cfg.index_url("jakarta-pusat", "rumah", district="gambir")
        == f"{DEFAULT_BASE_URL}/jual/jakarta-pusat/gambir/rumah/"
    )
    assert (
        cfg.index_url("jakarta-pusat", "rumah", page=2, district="gambir")
        == f"{DEFAULT_BASE_URL}/jual/jakarta-pusat/gambir/rumah/?page=2"
    )


def test_config_is_immutable() -> None:
    cfg = Config.from_env()
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.max_retries = 99  # type: ignore[misc]
