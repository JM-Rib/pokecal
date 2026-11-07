"""Store URL parser and query parameter extractor."""

from __future__ import annotations

import urllib.parse
from pokecal.models import StoreMetadata
from pokecal.timezone import resolve_timezone


def parse_store_url(
    url: str,
    fallback_name: str = "Pokémon Store",
    default_timezone: str = "Europe/Paris",
) -> StoreMetadata:
    """Parse a Play! Pokémon Event Locator store URL to extract metadata.

    Extracts:
    - LocationGuid / store GUID
    - Store name
    - Latitude and Longitude
    - Locale
    - Timezone (resolved offline via coordinates)
    """
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)

    # Helper to get first parameter value matching candidates
    def get_first(*keys: str) -> str | None:
        for key in keys:
            # Case-insensitive check
            for actual_key, values in params.items():
                if actual_key.lower() == key.lower() and values and values[0].strip():
                    return values[0].strip()
        return None

    location_guid = get_first("LocationGuid", "location_guid", "locationId", "guid") or ""
    store_name = get_first("storename", "LocationName", "name", "store") or fallback_name
    locale = get_first("locale", "lang") or "fr-FR"

    lat_str = get_first("latitude", "lat")
    lon_str = get_first("longitude", "lng", "lon")

    latitude: float | None = None
    longitude: float | None = None

    if lat_str:
        try:
            latitude = float(lat_str)
        except ValueError:
            pass

    if lon_str:
        try:
            longitude = float(lon_str)
        except ValueError:
            pass

    resolved_tz = resolve_timezone(latitude, longitude, default_timezone=default_timezone)

    return StoreMetadata(
        location_guid=location_guid,
        name=store_name,
        latitude=latitude,
        longitude=longitude,
        locale=locale,
        timezone=resolved_tz,
        original_url=url,
    )
