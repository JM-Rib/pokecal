"""Sync orchestration: shared per-store scraping, per-user feeds, fault isolation."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from pokecal.db import StoreRepository
from pokecal.models import PokemonEvent, StoreConfig, StoreFilterConfig, UserStore
from pokecal.scraper import filter_events

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    succeeded: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def sync_users(
    repo: StoreRepository,
    user_ids: Sequence[str],
    scrape_store: Callable[[StoreConfig], list[PokemonEvent]],
    export: Callable[[str, list[PokemonEvent]], None],
) -> SyncResult:
    """Scrape each distinct store once and export each user's feed.

    Stores are scraped unfiltered and shared by every user referencing them; each user's
    own filters are applied afterwards. A store failure fails only the users who have it
    enabled, and a failed user keeps their previous file.
    """
    result = SyncResult()
    user_stores = {uid: [s for s in repo.list_stores(uid) if s.enabled] for uid in user_ids}
    cache: dict[str, list[PokemonEvent] | Exception] = {}

    def events_for(store: UserStore) -> list[PokemonEvent]:
        if store.location_guid not in cache:
            try:
                cache[store.location_guid] = scrape_store(
                    StoreConfig(name=store.name, url=store.url, filters=StoreFilterConfig(game_categories=[]))
                )
            except Exception as exc:
                logger.error("Scrape failed for store %s: %s", store.name, exc)
                cache[store.location_guid] = exc
        cached = cache[store.location_guid]
        if isinstance(cached, Exception):
            raise cached
        return cached

    for user_id, stores in user_stores.items():
        try:
            events: list[PokemonEvent] = []
            for store in stores:
                events.extend(filter_events(events_for(store), store.filters))
            export(user_id, events)
        except Exception as exc:
            logger.error("Sync failed for user %s: %s", user_id, exc)
            result.failed[user_id] = str(exc)
        else:
            result.succeeded.append(user_id)
    return result
