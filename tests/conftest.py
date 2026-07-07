"""Shared test fixtures.

This standalone service ships only the DB-free tests (API + parsing + config +
fetcher), so no database fixtures are needed here.
"""

from __future__ import annotations

from scraper import config  # noqa: F401  (import for load_dotenv side effect)
