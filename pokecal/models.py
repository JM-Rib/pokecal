"""Data models for PokéCal."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any
from pydantic import BaseModel, Field


class StoreMetadata(BaseModel):
    """Metadata for a target Pokémon store/league venue."""

    location_guid: str
    name: str
    latitude: float | None = None
    longitude: float | None = None
    locale: str = "en-US"
    timezone: str = "UTC"
    address: str | None = None
    original_url: str | None = None


class SearchedStore(BaseModel):
    """A store returned by the locator's nearby-store search."""

    guid: str
    name: str
    address: str = ""
    latitude: float | None = None
    longitude: float | None = None


class StoreFilterConfig(BaseModel):
    """Filter preferences for a specific store."""

    game_categories: list[str] = Field(default_factory=lambda: ["TCG"])
    event_types: list[str] | None = None
    exclude_keywords: list[str] = Field(default_factory=list)


class StoreConfig(BaseModel):
    """Store definition from configuration."""

    name: str
    url: str
    enabled: bool = True
    filters: StoreFilterConfig = Field(default_factory=StoreFilterConfig)


class UserStore(StoreConfig):
    """A user's favorite of a shared store, with the user's own enabled flag and filters."""

    location_guid: str


class PokéCalConfig(BaseModel):
    """Output settings loaded from environment variables."""

    calendar_name: str = "Pokémon TCG Events"
    calendar_description: str = "Pokémon TCG Tournaments and League Events synchronized by PokéCal"
    output_dir: str = "dist"
    default_timezone: str = "Europe/Paris"


class PokemonEvent(BaseModel):
    """Normalized Pokémon tournament or league event."""

    guid: str
    store_guid: str
    store_name: str
    title: str
    game_category: str = "TCG"
    event_type: str = "Tournament"
    format: str | None = None
    start_time: datetime
    end_time: datetime | None = None
    timezone: str = "UTC"
    cost: str | None = None
    registration_info: str | None = None
    status: str = "CONFIRMED"
    url: str | None = None
    location_name: str | None = None
    location_address: str | None = None
    description: str | None = None
    raw_data: dict[str, Any] = Field(default_factory=dict)

    def get_uid(self, domain: str = "pokecal") -> str:
        """Generate a deterministic, idempotent RFC 5545 UID.

        If a unique event GUID exists from the provider, use it directly.
        Otherwise, build a stable hash from store_guid, start_time, and title.
        """
        if self.guid and self.guid.strip() and not self.guid.startswith("temp-"):
            clean_guid = self.guid.strip().lower()
            return f"pokemon-event-{clean_guid}@{domain}"

        # Deterministic fallback hash
        start_str = self.start_time.strftime("%Y%m%dT%H%M%S")
        slug_seed = f"{self.store_guid}:{start_str}:{self.title.strip().lower()}"
        hash_val = hashlib.sha256(slug_seed.encode("utf-8")).hexdigest()[:16]
        date_slug = self.start_time.strftime("%Y%m%d")
        return f"pokemon-tcg-{self.store_guid}-{date_slug}-{hash_val}@{domain}"

    def effective_end_time(self, default_duration_hours: float = 4.0) -> datetime:
        """Return end_time or default to start_time + default_duration_hours."""
        if self.end_time:
            return self.end_time
        return self.start_time + timedelta(hours=default_duration_hours)
