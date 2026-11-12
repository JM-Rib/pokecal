"""Per-user sync orchestration with fault isolation."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from pokecal.db import StoreRepository
from pokecal.models import PokemonEvent, StoreConfig

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    succeeded: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def sync_users(
    repo: StoreRepository,
    user_ids: Sequence[str],
    scrape: Callable[[Sequence[StoreConfig]], list[PokemonEvent]],
    export: Callable[[str, list[PokemonEvent]], None],
) -> SyncResult:
    """Scrape and export each user's feed; one user's failure never affects the others.

    A user's feed is only exported after all of their enabled stores were scraped,
    so a failed user keeps their previous file.
    """
    result = SyncResult()
    for user_id in user_ids:
        try:
            stores = [s for s in repo.list_stores(user_id) if s.enabled]
            events = scrape(stores)
            export(user_id, events)
        except Exception as exc:
            logger.error("Sync failed for user %s: %s", user_id, exc)
            result.failed[user_id] = str(exc)
        else:
            result.succeeded.append(user_id)
    return result
