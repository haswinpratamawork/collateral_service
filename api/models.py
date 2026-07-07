"""API response model."""

from __future__ import annotations

from pydantic import BaseModel


class ExtractResult(BaseModel):
    """The four enriched fields for a Rumah123 listing."""

    luas_tanah: float | None = None       # land area (LT), m²
    luas_bangunan: float | None = None    # building area (LB), m²
    kode_pos: str | None = None           # postal code (via reverse geocoding)
    kelurahan: str | None = None          # village (via reverse geocoding)
