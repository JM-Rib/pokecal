"""Offline timezone resolution from geographic coordinates."""

from __future__ import annotations

import logging
from typing import Optional
from timezonefinder import TimezoneFinder

logger = logging.getLogger(__name__)

_tf_instance: Optional[TimezoneFinder] = None


def get_timezone_finder() -> TimezoneFinder:
    """Return a cached TimezoneFinder instance."""
    global _tf_instance
    if _tf_instance is None:
        _tf_instance = TimezoneFinder()
    return _tf_instance


def resolve_timezone(
    latitude: float | None,
    longitude: float | None,
    default_timezone: str = "Europe/Paris",
) -> str:
    """Resolve an IANA timezone identifier from latitude and longitude.

    Uses offline timezone shapefiles via timezonefinder.
    If coordinates are absent or resolution fails, falls back to default_timezone.
    """
    if latitude is None or longitude is None:
        return default_timezone

    try:
        tf = get_timezone_finder()
        tz_name = tf.timezone_at(lat=latitude, lng=longitude)
        if tz_name:
            return tz_name
        # Fallback to closest timezone if slightly offshore/boundary
        tz_name = tf.closest_timezone_at(lat=latitude, lng=longitude)
        if tz_name:
            return tz_name
    except Exception as exc:
        logger.warning(
            "Failed to resolve timezone for (%s, %s): %s. Using default %s.",
            latitude,
            longitude,
            exc,
            default_timezone,
        )

    return default_timezone
