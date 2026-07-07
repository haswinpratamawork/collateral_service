"""Typed listing record — the clean shape persisted to the ``listings`` table.

Field names match the table columns written by ``Repository.upsert_listing`` exactly, so
``ListingRecord(...).model_dump()`` can be handed straight to the repository.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ListingRecord(BaseModel):
    listing_id: str
    source: str = "rumah123"
    url: str | None = None
    title: str | None = None
    property_type: str | None = None

    province: str | None = None
    city: str | None = None
    district: str | None = None
    area: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    price_idr: int | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    land_area_m2: float | None = None
    building_area_m2: float | None = None
    certificate: str | None = None

    # Source's own dates from Rumah123 ("dibuat" / "diperbarui").
    listing_created_at: datetime | None = None
    listing_updated_at: datetime | None = None

    extra_specs: dict[str, Any] = Field(default_factory=dict)
    agent_name: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
