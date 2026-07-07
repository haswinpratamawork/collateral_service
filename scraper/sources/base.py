"""Source interface: how the pipeline discovers and parses listings for one site."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any


class Source(ABC):
    """A property-listing source (one website)."""

    name: str
    # Set True by discover() if any index page failed to fetch (e.g. network/rate-limit),
    # meaning the crawl is partial and delisting must NOT run (can't tell gone vs unseen).
    discovery_incomplete: bool = False

    @abstractmethod
    def discover(self) -> Iterator[str]:
        """Yield absolute URLs of listing detail pages to scrape this run."""

    @abstractmethod
    def parse(self, html: str) -> dict[str, Any]:
        """Parse a listing detail page's HTML into a raw record dict.

        Normalization into typed fields happens later (Phase 4); this returns the
        source's values close to as-found. Raises ValueError if no listing is found.
        """

    def matches_scope(self, raw: dict[str, Any]) -> bool:
        """Whether a parsed raw record falls within this source's requested scope.

        Default: everything is in scope. A source scoped to a district overrides this to
        reject out-of-area listings (e.g. promoted ads that appear on every results page).
        """
        return True
