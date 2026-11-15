"""Unit tests for shared-store sync orchestration."""

from datetime import datetime

from pokecal.models import PokemonEvent, StoreFilterConfig, UserStore
from pokecal.sync import sync_users


class FakeRepo:
    def __init__(self, stores):
        self.stores = stores

    def list_stores(self, user_id):
        return self.stores[user_id]


def store(guid, **kw):
    return UserStore(location_guid=guid, name=guid, url=f"https://x/{guid}", **kw)


def event(guid, category="TCG"):
    return PokemonEvent(
        guid=f"{guid}-{category}",
        store_guid=guid,
        store_name=guid,
        title=f"{guid} {category}",
        game_category=category,
        start_time=datetime(2026, 1, 1),
    )


def test_sync_users_scrapes_shared_store_once_and_applies_user_filters():
    repo = FakeRepo(
        {
            "1": [store("a")],
            "2": [store("a", filters=StoreFilterConfig(game_categories=["VGC"])), store("b")],
            "3": [store("a", enabled=False)],
        }
    )
    scraped = []
    exported = {}

    def scrape_store(cfg):
        scraped.append(cfg.url)
        guid = cfg.url.rsplit("/", 1)[1]
        return [event(guid, "TCG"), event(guid, "VGC")]

    result = sync_users(repo, ["1", "2", "3"], scrape_store, lambda uid, evs: exported.__setitem__(uid, evs))

    assert sorted(scraped) == ["https://x/a", "https://x/b"]
    assert result.succeeded == ["1", "2", "3"]
    assert [e.title for e in exported["1"]] == ["a TCG"]
    assert [e.title for e in exported["2"]] == ["a VGC", "b TCG"]
    assert exported["3"] == []


def test_sync_users_store_failure_only_fails_users_with_that_store():
    repo = FakeRepo({"1": [store("ok")], "2": [store("boom")], "3": [store("boom", enabled=False)]})
    exported = {}
    calls = []

    def scrape_store(cfg):
        calls.append(cfg.url)
        if cfg.url.endswith("boom"):
            raise RuntimeError("scrape failed")
        return []

    result = sync_users(repo, ["1", "2", "3"], scrape_store, lambda uid, evs: exported.__setitem__(uid, evs))

    assert result.succeeded == ["1", "3"]
    assert result.failed == {"2": "scrape failed"}
    assert set(exported) == {"1", "3"}
    assert calls == ["https://x/ok", "https://x/boom"]
