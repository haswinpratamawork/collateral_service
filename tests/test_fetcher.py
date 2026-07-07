"""Tests for scraper.fetch.httpx_fetcher (Phase 2). No live HTTP — httpx MockTransport."""

from __future__ import annotations

import random

import httpx
import pytest

from scraper.config import Config
from scraper.fetch.base import FetchError, RobotsDisallowed
from scraper.fetch.httpx_fetcher import HttpxFetcher, RobotsPolicy


def _config(**overrides) -> Config:
    base = {"request_delay_min": 0.0, "request_delay_max": 0.0, "max_retries": 3}
    base.update(overrides)
    return Config(**base)


class _Recorder:
    """A sleep stand-in that records the durations it was asked to sleep."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def _allow_all() -> RobotsPolicy:
    return RobotsPolicy("ua", fetch_text=lambda _url: None)


def _fetcher(handler, *, config=None, sleep=None, rng=None, robots=None) -> HttpxFetcher:
    transport = httpx.MockTransport(handler)
    return HttpxFetcher(
        config or _config(),
        transport=transport,
        sleep=sleep or _Recorder(),
        rng=rng or random.Random(0),
        robots=robots if robots is not None else _allow_all(),
    )


def test_get_success_sends_user_agent() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers.get("user-agent", "")
        return httpx.Response(200, text="<html>ok</html>")

    cfg = _config(user_agent="house-scrapping/test")
    body = _fetcher(handler, config=cfg).get("https://example.com/page")

    assert body == "<html>ok</html>"
    assert seen["ua"] == "house-scrapping/test"


def test_retries_on_503_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, text="recovered")

    sleep = _Recorder()
    body = _fetcher(handler, sleep=sleep).get("https://example.com/x")

    assert body == "recovered"
    assert calls["n"] == 2
    assert sleep.calls  # backoff slept at least once


def test_gives_up_after_max_retries() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503)

    with pytest.raises(FetchError):
        _fetcher(handler, config=_config(max_retries=3)).get("https://example.com/x")
    assert calls["n"] == 3  # exactly max_retries attempts


def test_non_retryable_4xx_fails_fast() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404)

    with pytest.raises(FetchError):
        _fetcher(handler).get("https://example.com/missing")
    assert calls["n"] == 1  # not retried


def test_throttle_delay_within_configured_range() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    sleep = _Recorder()
    cfg = _config(request_delay_min=2.0, request_delay_max=2.0)
    _fetcher(handler, config=cfg, sleep=sleep).get("https://example.com/x")

    assert 2.0 in sleep.calls  # throttle slept the configured amount


def test_robots_disallow_blocks_url() -> None:
    robots_txt = "User-agent: *\nDisallow: /private/\n"
    robots = RobotsPolicy("house-scrapping/test", fetch_text=lambda _url: robots_txt)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="ok")

    cfg = _config(user_agent="house-scrapping/test")
    fetcher = _fetcher(handler, config=cfg, robots=robots)

    with pytest.raises(RobotsDisallowed):
        fetcher.get("https://example.com/private/secret")
    # an allowed path still works
    assert fetcher.get("https://example.com/jual/jakarta/rumah/") == "ok"
