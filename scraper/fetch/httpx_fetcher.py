"""httpx-based Fetcher (Approach A): polite, retrying, robots-aware.

Politeness and resilience live here so the rest of the pipeline never thinks about it:
- randomized delay before every request (config.request_delay_min/max)
- exponential-backoff retries on 429/5xx and transport/timeout errors
- a real User-Agent header
- robots.txt respected per host

Time and randomness are injectable (``sleep``, ``rng``) so tests are fast and deterministic.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from scraper.config import Config
from scraper.fetch.base import Fetcher, FetchError, RobotsDisallowed

# Statuses worth retrying (transient). Other 4xx are permanent and fail fast.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class _Retryable(FetchError):
    """Internal: a transient failure that should trigger a retry."""


class RobotsPolicy:
    """Caches and evaluates robots.txt per host. Missing/unfetchable robots = allow all."""

    def __init__(self, user_agent: str, fetch_text: Callable[[str], str | None]) -> None:
        self._user_agent = user_agent
        self._fetch_text = fetch_text
        self._cache: dict[tuple[str, str], RobotFileParser | None] = {}

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        host = (parts.scheme, parts.netloc)
        if host not in self._cache:
            self._cache[host] = self._load(f"{parts.scheme}://{parts.netloc}/robots.txt")
        parser = self._cache[host]
        if parser is None:  # no robots.txt available -> nothing disallowed
            return True
        return parser.can_fetch(self._user_agent, url)

    def _load(self, robots_url: str) -> RobotFileParser | None:
        try:
            text = self._fetch_text(robots_url)
        except Exception:
            text = None
        if text is None:
            return None
        parser = RobotFileParser()
        parser.parse(text.splitlines())
        return parser


class HttpxFetcher(Fetcher):
    def __init__(
        self,
        config: Config,
        *,
        client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
        robots: RobotsPolicy | None = None,
    ) -> None:
        self._config = config
        self._client = client or httpx.Client(
            headers={"User-Agent": config.user_agent},
            timeout=30.0,
            follow_redirects=True,
            transport=transport,
        )
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._robots = robots if robots is not None else RobotsPolicy(
            config.user_agent, self._fetch_robots_text
        )

    # --- public -----------------------------------------------------------------

    def get(self, url: str) -> str:
        if not self._robots.allowed(url):
            raise RobotsDisallowed(url)
        retrying = Retrying(
            stop=stop_after_attempt(self._config.max_retries),
            wait=wait_exponential(multiplier=0.5, max=30),
            retry=retry_if_exception_type(_Retryable),
            sleep=self._sleep,
            reraise=True,
        )
        for attempt in retrying:
            with attempt:
                self._throttle()
                return self._request(url)
        raise FetchError(url)  # unreachable; satisfies type checkers

    def close(self) -> None:
        self._client.close()

    # --- internals --------------------------------------------------------------

    def _throttle(self) -> None:
        delay = self._rng.uniform(
            self._config.request_delay_min, self._config.request_delay_max
        )
        if delay > 0:
            self._sleep(delay)

    def _request(self, url: str) -> str:
        try:
            resp = self._client.get(url)
        except httpx.TransportError as exc:  # connect/read/timeout -> retry
            raise _Retryable(str(exc)) from exc
        if resp.status_code in RETRYABLE_STATUS:
            raise _Retryable(f"HTTP {resp.status_code} for {url}")
        if resp.is_error:  # other 4xx -> permanent, don't retry
            raise FetchError(f"HTTP {resp.status_code} for {url}")
        return resp.text

    def _fetch_robots_text(self, robots_url: str) -> str | None:
        resp = self._client.get(robots_url)
        return resp.text if resp.status_code == 200 else None
