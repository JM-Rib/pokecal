"""Unit tests for per-user sync orchestration."""

from pokecal.models import StoreConfig
from pokecal.sync import sync_users


class FakeRepo:
    def __init__(self, stores):
        self.stores = stores

    def list_stores(self, user_id):
        return self.stores[user_id]


def test_sync_users_isolates_failures_and_skips_export_for_failed_user():
    repo = FakeRepo(
        {
            "1": [StoreConfig(name="ok", url="u1")],
            "2": [StoreConfig(name="boom", url="u2")],
            "3": [StoreConfig(name="off", url="u3", enabled=False)],
        }
    )
    exported = {}

    def scrape(stores):
        if any(s.name == "boom" for s in stores):
            raise RuntimeError("scrape failed")
        return [s.name for s in stores]

    result = sync_users(repo, ["1", "2", "3"], scrape, lambda uid, evs: exported.__setitem__(uid, evs))

    assert result.succeeded == ["1", "3"]
    assert result.failed == {"2": "scrape failed"}
    assert exported == {"1": ["ok"], "3": []}
