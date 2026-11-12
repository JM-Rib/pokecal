"""Per-user store persistence (Postgres) behind a swappable repository interface."""

from __future__ import annotations

import re
from typing import Protocol

import psycopg
from psycopg.types.json import Jsonb

from pokecal.models import StoreConfig, StoreFilterConfig, UserStore

# Discord user IDs are snowflakes: unsigned 64-bit integers, exchanged as strings by the API.
# They are stored as TEXT because Postgres BIGINT is signed and cannot hold the full range.
MAX_SNOWFLAKE = 2**64 - 1


def validate_user_id(user_id: str) -> str:
    """Return the canonical Discord snowflake string or raise ValueError."""
    candidate = user_id.strip()
    if not re.fullmatch(r"[0-9]{1,20}", candidate) or not 0 < int(candidate) <= MAX_SNOWFLAKE:
        raise ValueError(f"Invalid Discord user ID: {user_id!r}")
    return str(int(candidate))


class StoreRepository(Protocol):
    """Storage of each user's favorite stores, their enabled flag and filters."""

    def add_favorite(self, user_id: str, store: StoreConfig, location_guid: str) -> bool:
        """Save a store for a user. Returns False if the user already has that LocationGuid."""
        ...

    def list_stores(self, user_id: str) -> list[UserStore]:
        """Return all of a user's stores, enabled or not."""
        ...

    def list_users(self) -> list[str]:
        """Return the IDs of all users that have at least one store."""
        ...


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    discord_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS stores (
    location_guid TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS user_stores (
    discord_id TEXT NOT NULL REFERENCES users(discord_id) ON DELETE CASCADE,
    location_guid TEXT NOT NULL REFERENCES stores(location_guid),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (discord_id, location_guid)
);
"""

# Older versions kept name/url on each user_stores row. Move them into the shared stores table.
LEGACY_COLUMN_CHECK = (
    "SELECT 1 FROM information_schema.columns "
    "WHERE table_schema = current_schema() AND table_name = 'user_stores' AND column_name = 'url'"
)
LEGACY_MIGRATION = """
INSERT INTO stores (location_guid, name, url, created_at)
SELECT DISTINCT ON (location_guid) location_guid, name, url, created_at
FROM user_stores ORDER BY location_guid, created_at
ON CONFLICT DO NOTHING;
ALTER TABLE user_stores
    ADD CONSTRAINT user_stores_location_guid_fkey FOREIGN KEY (location_guid) REFERENCES stores(location_guid);
ALTER TABLE user_stores DROP COLUMN name, DROP COLUMN url;
"""


class PostgresStoreRepository:
    """StoreRepository backed by Postgres; the schema is created on connect."""

    def __init__(self, conninfo: str) -> None:
        self.conn = psycopg.connect(conninfo, autocommit=True)
        self.conn.execute(SCHEMA)
        self._migrate_legacy()

    def _migrate_legacy(self) -> None:
        with self.conn.transaction():
            if self.conn.execute(LEGACY_COLUMN_CHECK).fetchone():
                self.conn.execute(LEGACY_MIGRATION)

    def close(self) -> None:
        self.conn.close()

    def add_favorite(self, user_id: str, store: StoreConfig, location_guid: str) -> bool:
        user_id = validate_user_id(user_id)
        with self.conn.transaction():
            self.conn.execute("INSERT INTO users (discord_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
            guid = location_guid.lower()
            self.conn.execute(
                "INSERT INTO stores (location_guid, name, url) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (guid, store.name, store.url),
            )
            cur = self.conn.execute(
                "INSERT INTO user_stores (discord_id, location_guid, enabled, filters) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (
                    user_id,
                    guid,
                    store.enabled,
                    Jsonb(store.filters.model_dump()),
                ),
            )
            return cur.rowcount == 1

    def list_stores(self, user_id: str) -> list[UserStore]:
        user_id = validate_user_id(user_id)
        rows = self.conn.execute(
            "SELECT s.location_guid, s.name, s.url, us.enabled, us.filters "
            "FROM user_stores us JOIN stores s USING (location_guid) "
            "WHERE us.discord_id = %s ORDER BY us.created_at, s.name",
            (user_id,),
        ).fetchall()
        return [
            UserStore(location_guid=g, name=n, url=u, enabled=e, filters=StoreFilterConfig(**(f or {})))
            for g, n, u, e, f in rows
        ]

    def list_users(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT discord_id FROM user_stores ORDER BY discord_id"
        ).fetchall()
        return [r[0] for r in rows]
