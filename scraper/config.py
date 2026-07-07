"""Runtime configuration: scrape targets, throttle settings, and database DSN.

Values come from environment variables (optionally loaded from a local ``.env``).
``python-dotenv`` is optional at import time so this module — and its tests — run with
nothing but the standard library installed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

try:  # optional, so config (and its tests) work without dependencies installed
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - exercised only when dotenv is absent
    pass

# Jabodetabek city slugs as used in Rumah123 listing URLs (/jual/{city}/{type}/).
JABODETABEK_CITIES: tuple[str, ...] = (
    "jakarta-pusat",
    "jakarta-utara",
    "jakarta-barat",
    "jakarta-selatan",
    "jakarta-timur",
    "bogor",
    "depok",
    "tangerang",
    "tangerang-selatan",
    "bekasi",
)

# Rumah123 "dijual" (for-sale) property-type slugs -> normalized property_type.
PROPERTY_TYPES: dict[str, str] = {
    "rumah": "house",
    "apartemen": "apartment",
    "tanah": "land",
    "ruko": "shophouse",
    "gudang": "warehouse",
}

# Defaults shared by the dataclass fields and ``from_env`` so they never drift apart.
DEFAULT_USER_AGENT = (
    "house-scrapping/0.1 (+https://github.com/haswinpratamawork/house_scrapping)"
)
DEFAULT_DELAY_MIN = 2.0
DEFAULT_DELAY_MAX = 5.0
DEFAULT_MAX_CONCURRENCY = 2
DEFAULT_MAX_RETRIES = 4
DEFAULT_BASE_URL = "https://www.rumah123.com"


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, "") else default


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


@dataclass(frozen=True)
class Config:
    """Immutable scraper configuration."""

    database_url: str = ""
    user_agent: str = DEFAULT_USER_AGENT
    request_delay_min: float = DEFAULT_DELAY_MIN
    request_delay_max: float = DEFAULT_DELAY_MAX
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    max_retries: int = DEFAULT_MAX_RETRIES
    base_url: str = DEFAULT_BASE_URL
    cities: tuple[str, ...] = JABODETABEK_CITIES
    property_types: tuple[str, ...] = field(default=tuple(PROPERTY_TYPES.keys()))

    @classmethod
    def from_env(cls) -> Config:
        """Build a Config from environment variables, falling back to defaults."""
        return cls(
            database_url=os.getenv("DATABASE_URL", ""),
            user_agent=os.getenv("USER_AGENT", DEFAULT_USER_AGENT),
            request_delay_min=_get_float("REQUEST_DELAY_MIN", DEFAULT_DELAY_MIN),
            request_delay_max=_get_float("REQUEST_DELAY_MAX", DEFAULT_DELAY_MAX),
            max_concurrency=_get_int("MAX_CONCURRENCY", DEFAULT_MAX_CONCURRENCY),
            max_retries=_get_int("MAX_RETRIES", DEFAULT_MAX_RETRIES),
            base_url=os.getenv("BASE_URL", DEFAULT_BASE_URL),
        )

    def index_url(
        self,
        city: str,
        property_type: str,
        page: int = 1,
        district: str | None = None,
    ) -> str:
        """URL of a for-sale listing index page.

        City level: ``/jual/{city}/{type}/``; district level (when ``district`` given):
        ``/jual/{city}/{district}/{type}/``.
        """
        location = f"{city}/{district}" if district else city
        base = f"{self.base_url}/jual/{location}/{property_type}/"
        return base if page <= 1 else f"{base}?page={page}"

    @staticmethod
    def normalized_property_type(slug: str) -> str:
        """Map a Rumah123 type slug to a normalized property_type ('other' if unknown)."""
        return PROPERTY_TYPES.get(slug, "other")
