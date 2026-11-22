"""Discord-agnostic command logic for the PokéCal bot (search, add, remove, list, filter)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from pokecal.db import StoreRepository
from pokecal.models import SearchedStore, StoreConfig, StoreFilterConfig, UserStore
from pokecal.search import build_location_detail_url

logger = logging.getLogger(__name__)

MAX_SEARCH_RESULTS = 25
CLEAR_WORDS = {"any", "all", "none", "clear"}

SearchFunc = Callable[[str], Awaitable[list[SearchedStore]]]


class BotError(Exception):
    """A user-facing problem; the message is safe to show in Discord."""


def parse_list(value: str) -> list[str]:
    """Split a comma-separated option into trimmed, non-empty, de-duplicated items."""
    return list(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))


def pick_by_name(query: str, items: list, name: Callable[[object], str], what: str):
    """Pick one item by 1-based number, exact name or unique substring (case-insensitive)."""
    query = query.strip()
    if not query:
        raise BotError(f"Tell me which {what} you mean.")
    if query.isdigit():
        index = int(query)
        if not 1 <= index <= len(items):
            raise BotError(f"No {what} number {index}.")
        return items[index - 1]
    needle = query.lower()
    exact = [i for i in items if name(i).lower() == needle]
    matches = exact or [i for i in items if needle in name(i).lower()]
    if not matches:
        raise BotError(f"No {what} matches '{query}'.")
    if len(matches) > 1:
        names = ", ".join(name(i) for i in matches[:5])
        raise BotError(f"'{query}' matches several {what}s ({names}); be more specific or use its number.")
    return matches[0]


def format_filters(filters: StoreFilterConfig) -> str:
    parts = [
        f"games: {', '.join(filters.game_categories) or 'all'}",
        f"types: {', '.join(filters.event_types) if filters.event_types else 'all'}",
    ]
    if filters.exclude_keywords:
        parts.append(f"excluding: {', '.join(filters.exclude_keywords)}")
    return "; ".join(parts)


class BotService:
    """Per-user store management. Search results are kept in memory only (they are transient)."""

    def __init__(self, repo: StoreRepository, search: SearchFunc, range_: int = 25, is_km: bool = False) -> None:
        self.repo = repo
        self.search_func = search
        self.range_ = range_
        self.is_km = is_km
        self.last_results: dict[str, list[SearchedStore]] = {}

    async def search(self, user_id: str, city: str) -> str:
        city = city.strip()
        if not city:
            raise BotError("Give me a city to search.")
        stores = (await self.search_func(city))[:MAX_SEARCH_RESULTS]
        self.last_results[user_id] = stores
        if not stores:
            return f"No stores found near '{city}'."
        lines = [f"{i}. **{s.name}** — {s.address}" if s.address else f"{i}. **{s.name}**" for i, s in enumerate(stores, 1)]
        return f"Stores near {city}:\n" + "\n".join(lines) + "\nUse `/add <number or name>` to save one."

    def add(self, user_id: str, store: str) -> str:
        results = self.last_results.get(user_id)
        if not results:
            raise BotError("Run `/search <city>` first, then add a store from the results.")
        found = pick_by_name(store, results, lambda s: s.name, "store from your last search")
        url = build_location_detail_url(found, range_=self.range_, is_km=self.is_km)
        if self.repo.add_favorite(user_id, StoreConfig(name=found.name, url=url), found.guid):
            return f"Added **{found.name}** to your favorites."
        return f"**{found.name}** is already in your favorites."

    def remove(self, user_id: str, store: str) -> str:
        found = self._favorite(user_id, store)
        if not self.repo.remove_favorite(user_id, found.location_guid):
            raise BotError(f"**{found.name}** is no longer in your favorites.")
        return f"Removed **{found.name}** from your favorites."

    def list(self, user_id: str) -> str:
        stores = self.repo.list_stores(user_id)
        if not stores:
            return "You have no favorite stores yet. Use `/search <city>` to find some."
        lines = [
            f"{i}. **{s.name}**{'' if s.enabled else ' (disabled)'} — {format_filters(s.filters)}"
            for i, s in enumerate(stores, 1)
        ]
        return "Your favorite stores:\n" + "\n".join(lines)

    def filter(
        self,
        user_id: str,
        store: str,
        event_types: str | None = None,
        game_categories: str | None = None,
        exclude_keywords: str | None = None,
        enabled: bool | None = None,
    ) -> str:
        """Update the provided options only; "any"/"none" clears a list. Event types match as substrings."""
        found = self._favorite(user_id, store)
        filters = found.filters.model_copy(deep=True)
        if event_types is not None:
            items = parse_list(event_types)
            filters.event_types = None if not items or items[0].lower() in CLEAR_WORDS else items
        if game_categories is not None:
            items = parse_list(game_categories)
            filters.game_categories = [] if not items or items[0].lower() in CLEAR_WORDS else [g.upper() for g in items]
        if exclude_keywords is not None:
            items = parse_list(exclude_keywords)
            filters.exclude_keywords = [] if not items or items[0].lower() in CLEAR_WORDS else items
        new_enabled = found.enabled if enabled is None else enabled
        if not self.repo.update_store(user_id, found.location_guid, new_enabled, filters):
            raise BotError(f"**{found.name}** is no longer in your favorites.")
        state = "" if new_enabled else " (disabled)"
        return f"Updated **{found.name}**{state}: {format_filters(filters)}"

    def _favorite(self, user_id: str, store: str) -> UserStore:
        stores = self.repo.list_stores(user_id)
        if not stores:
            raise BotError("You have no favorite stores yet. Use `/search <city>` to find some.")
        return pick_by_name(store, stores, lambda s: s.name, "favorite")

    def favorite_names(self, user_id: str) -> list[str]:
        return [s.name for s in self.repo.list_stores(user_id)]

    def result_names(self, user_id: str) -> list[str]:
        return [s.name for s in self.last_results.get(user_id, [])]
