"""Fetcher interface and error types.

The pipeline depends only on this interface, so the HTTP implementation (httpx today,
Playwright later) can be swapped without touching anything downstream.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class FetchError(Exception):
    """A page could not be fetched (after any retries)."""


class RobotsDisallowed(FetchError):
    """The URL is disallowed by the site's robots.txt for our User-Agent."""


class Fetcher(ABC):
    """Fetches the text body of a URL, handling throttling and retries internally."""

    @abstractmethod
    def get(self, url: str) -> str:
        """Return the response body for ``url``.

        Raises ``RobotsDisallowed`` if robots.txt forbids it, or ``FetchError`` if the
        request fails after retries.
        """
