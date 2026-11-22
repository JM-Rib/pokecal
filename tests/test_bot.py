"""Unit tests for the Discord-agnostic bot command logic."""

import asyncio

import pytest

from pokecal.bot import BotError, BotService
from pokecal.models import SearchedStore, StoreFilterConfig, UserStore


class FakeRepo:
    def __init__(self):
        self.stores: dict[str, dict[str, UserStore]] = {}

    def add_favorite(self, user_id, store, location_guid):
        mine = self.stores.setdefault(user_id, {})
        if location_guid in mine:
            return False
        mine[location_guid] = UserStore(location_guid=location_guid, **store.model_dump())
        return True

    def remove_favorite(self, user_id, location_guid):
        return self.stores.get(user_id, {}).pop(location_guid, None) is not None

    def update_store(self, user_id, location_guid, enabled, filters):
        current = self.stores.get(user_id, {}).get(location_guid)
        if current is None:
            return False
        self.stores[user_id][location_guid] = current.model_copy(update={"enabled": enabled, "filters": filters})
        return True

    def list_stores(self, user_id):
        return list(self.stores.get(user_id, {}).values())


STORES = [
    SearchedStore(guid="g1", name="Games Lyon", address="1 rue A", latitude=45.7, longitude=4.8),
    SearchedStore(guid="g2", name="Games Paris", address="2 rue B", latitude=48.8, longitude=2.3),
    SearchedStore(guid="g3", name="Comics Lyon", latitude=45.7, longitude=4.8),
]


def make_service(results=STORES):
    async def search(city):
        return results if city == "Lyon" else []

    return BotService(FakeRepo(), search)


def test_search_then_add_by_number_and_name_keeps_store_own_guid_and_coordinates():
    svc = make_service()
    text = asyncio.run(svc.search("1", "Lyon"))
    assert "1. **Games Lyon**" in text

    assert "Added" in svc.add("1", "2")
    assert "Added" in svc.add("1", "comics")
    assert "already" in svc.add("1", "Games Paris")
    stored = {s.location_guid: s for s in svc.repo.list_stores("1")}
    assert set(stored) == {"g2", "g3"}
    assert "LocationGuid=g2" in stored["g2"].url and "latitude=48.8" in stored["g2"].url


def test_add_duplicate_and_ambiguous_and_unknown():
    svc = make_service()
    asyncio.run(svc.search("1", "Lyon"))
    svc.add("1", "1")
    assert "already" in svc.add("1", "Games Lyon")
    with pytest.raises(BotError, match="several"):
        svc.add("1", "games")
    with pytest.raises(BotError, match="No store"):
        svc.add("1", "nothing")
    with pytest.raises(BotError, match="number 9"):
        svc.add("1", "9")


def test_add_requires_a_search_and_results_are_per_user():
    svc = make_service()
    asyncio.run(svc.search("1", "Lyon"))
    with pytest.raises(BotError, match="/search"):
        svc.add("2", "1")


def test_search_without_results_reports_it():
    svc = make_service()
    assert "No stores" in asyncio.run(svc.search("1", "Nowhere"))
    with pytest.raises(BotError):
        asyncio.run(svc.search("1", "  "))


def test_remove_and_list():
    svc = make_service()
    assert "no favorite" in svc.list("1")
    asyncio.run(svc.search("1", "Lyon"))
    svc.add("1", "1")
    svc.add("1", "2")
    assert "Games Paris" in svc.list("1")
    assert "Removed **Games Lyon**" in svc.remove("1", "lyon")
    assert [s.name for s in svc.repo.list_stores("1")] == ["Games Paris"]
    with pytest.raises(BotError):
        svc.remove("1", "lyon")


def test_filter_updates_only_given_options_and_can_clear():
    svc = make_service()
    asyncio.run(svc.search("1", "Lyon"))
    svc.add("1", "1")

    svc.filter("1", "1", event_types="League, Cup", exclude_keywords="Casual", game_categories="tcg,vgc")
    f = svc.repo.list_stores("1")[0].filters
    assert f == StoreFilterConfig(
        game_categories=["TCG", "VGC"], event_types=["League", "Cup"], exclude_keywords=["Casual"]
    )

    svc.filter("1", "Games Lyon", exclude_keywords="none", enabled=False)
    store = svc.repo.list_stores("1")[0]
    assert store.filters.event_types == ["League", "Cup"]
    assert store.filters.exclude_keywords == []
    assert store.enabled is False

    svc.filter("1", "1", event_types="any")
    assert svc.repo.list_stores("1")[0].filters.event_types is None
    with pytest.raises(BotError):
        svc.filter("2", "1", event_types="League")
