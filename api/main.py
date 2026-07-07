"""FastAPI app exposing GET /extract?url=<rumah123 listing url>.

Run: uvicorn api.main:app --reload  (needs GOOGLE_MAPS_API_KEY in the environment).
"""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI, HTTPException, Query

from api.geocode import GoogleGeocoder
from api.models import ExtractResult
from api.service import ListingService
from scraper.fetch.base import FetchError

app = FastAPI(
    title="Rumah123 Listing Extractor",
    description="Given a Rumah123 listing URL, return luas tanah, luas bangunan, "
    "kode pos, and kelurahan.",
)

_service: ListingService | None = None


def get_service() -> ListingService:
    """Build (once) and return the ListingService. Overridable in tests."""
    global _service
    if _service is None:
        api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        if not api_key:
            raise HTTPException(500, "GOOGLE_MAPS_API_KEY is not set")
        _service = ListingService(GoogleGeocoder(api_key))
    return _service


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/extract", response_model=ExtractResult)
def extract(
    url: str = Query(..., description="A rumah123.com/properti/... listing URL"),
    service: ListingService = Depends(get_service),
) -> ExtractResult:
    if "rumah123.com/properti/" not in url:
        raise HTTPException(400, "url must be a rumah123.com listing URL")
    try:
        return service.extract(url)
    except FetchError as exc:
        raise HTTPException(502, f"could not fetch listing: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(422, f"could not parse listing: {exc}") from exc
