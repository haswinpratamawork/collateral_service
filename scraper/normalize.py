"""Turn a source's raw record (Phase 3) into a clean, typed ListingRecord.

Rumah123 gives us mostly-clean values already (price is an integer), so the work here is:
map the Indonesian property-type label, coerce numeric specs from strings like "136 m²",
normalize the certificate code, and drop the obfuscated lat/long (where lat == long).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from scraper.models import ListingRecord

# Rumah123 listingType label -> normalized property_type.
_LABEL_TO_TYPE = {
    "rumah": "house",
    "apartemen": "apartment",
    "kondominium": "apartment",
    "tanah": "land",
    "ruko": "shophouse",
    "rukan": "shophouse",
    "gudang": "warehouse",
}

# attrs.common keys promoted to their own columns (kept out of extra_specs).
_PROMOTED_COMMON = {"bedroom", "bathroom", "landSize", "builtSize", "certificate", "listingType"}

_PRICE_UNITS = (
    ("triliun", 1_000_000_000_000),
    ("miliar", 1_000_000_000),
    ("milyar", 1_000_000_000),
    ("juta", 1_000_000),
    ("ribu", 1_000),
)


def _parse_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else None


def _parse_area(value: Any) -> float | None:
    """'136 m²' -> 136.0, '1.234 m²' -> 1234.0 ('.' is an ID thousands separator)."""
    if value in (None, ""):
        return None
    match = re.search(r"[\d.,]+", str(value))
    if not match:
        return None
    number = match.group().replace(".", "").replace(",", ".")
    try:
        return float(number)
    except ValueError:
        return None


def _parse_price_text(tag: Any) -> int | None:
    """Fallback price parse from 'Rp 3,87 Miliar' -> 3_870_000_000."""
    if not tag:
        return None
    text = str(tag).lower().replace("rp", "")
    multiplier = 1
    for word, factor in _PRICE_UNITS:
        if word in text:
            multiplier = factor
            text = text.replace(word, "")
            break
    match = re.search(r"[\d.,]+", text)
    if not match:
        return None
    number = match.group().replace(".", "").replace(",", ".")
    try:
        return int(round(float(number) * multiplier))
    except ValueError:
        return None


def _normalize_certificate(value: Any) -> str | None:
    if not value:
        return None
    code = str(value).split(" - ")[0].split("(")[0].strip()
    if not code:
        return None
    return code.upper() if len(code) <= 12 else code


def _property_type(label: Any) -> str:
    if not label:
        return "other"
    return _LABEL_TO_TYPE.get(str(label).strip().lower(), "other")


def _epoch_to_dt(value: Any) -> datetime | None:
    """Unix epoch seconds -> timezone-aware UTC datetime; None for non-numeric values."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except (ValueError, OverflowError, OSError):
        return None


def _coords(lat: Any, lon: Any) -> tuple[float | None, float | None]:
    """Return (lat, lon), or (None, None) when missing or obfuscated (lat == lon)."""
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return (None, None)
    if lat_f == lon_f or (lat_f == 0 and lon_f == 0):
        return (None, None)  # Rumah123 obfuscates coords as lat == lon
    return (lat_f, lon_f)


def _extra_specs(raw: dict[str, Any]) -> dict[str, Any]:
    """Collect remaining non-empty attribute values not promoted to columns."""
    out: dict[str, Any] = {}
    for section in ("attrs_common", "attrs_interior", "attrs_exterior", "attrs_other"):
        for key, value in (raw.get(section) or {}).items():
            if section == "attrs_common" and key in _PROMOTED_COMMON:
                continue
            if value in (None, ""):
                continue
            out[key] = value
    return out


def normalize(raw: dict[str, Any]) -> ListingRecord:
    """Map a Rumah123 raw record into a typed ListingRecord."""
    common = raw.get("attrs_common") or {}
    latitude, longitude = _coords(raw.get("latitude"), raw.get("longitude"))

    price = raw.get("price_offer")
    if price is None:
        price = _parse_price_text(raw.get("price_tag"))

    return ListingRecord(
        listing_id=raw["listing_id"],
        source=raw.get("source", "rumah123"),
        url=raw.get("url"),
        title=raw.get("title"),
        property_type=_property_type(raw.get("listing_type_label")),
        province=raw.get("province"),
        city=raw.get("city"),
        district=raw.get("district"),
        area=raw.get("area"),
        latitude=latitude,
        longitude=longitude,
        price_idr=price,
        bedrooms=_parse_int(common.get("bedroom")),
        bathrooms=_parse_int(common.get("bathroom")),
        land_area_m2=_parse_area(common.get("landSize")),
        building_area_m2=_parse_area(common.get("builtSize")),
        certificate=_normalize_certificate(common.get("certificate")),
        listing_created_at=_epoch_to_dt(raw.get("created_ts")),
        listing_updated_at=_epoch_to_dt(raw.get("updated_ts")),
        extra_specs=_extra_specs(raw),
        agent_name=raw.get("agent_name"),
        raw=raw.get("raw") or {},
    )
