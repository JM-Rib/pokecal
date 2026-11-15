"""Per-user store persistence (Postgres) behind a swappable repository interface."""

from __future__ import annotations

import re
import secrets
from typing import Protocol

import psycopg
from psycopg.types.json import Jsonb

from pokecal.models import StoreConfig, StoreFilterConfig, UserStore

# Discord user IDs are snowflakes: unsigned 64-bit integers, exchanged as strings by the API.
# They are stored as TEXT because Postgres BIGINT is signed and cannot hold the full range.
MAX_SNOWFLAKE = 2**64 - 1


def new_feed_token() -> str:
    """Return a random, URL-safe token used as the name of a user's public feed."""
    return secrets.token_urlsafe(32)


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

    def get_feed_token(self, user_id: str) -> str:
        """Return the user's stable feed token, creating it on first use."""
        ...

    def regenerate_feed_token(self, user_id: str) -> str:
        """Replace the user's feed token with a new random one and return it."""
        ...


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    discord_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE users ADD COLUMN IF NOT EXISTS feed_token TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS users_feed_token_key ON users (feed_token);
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


class PostgresStoreRepository:
    """StoreRepository backed by Postgres; the schema is created on connect."""

    def __init__(self, conninfo: str) -> None:
        self.conn = psycopg.connect(conninfo, autocommit=True)
        self.conn.execute(SCHEMA)

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

    def get_feed_token(self, user_id: str) -> str:
        user_id = validate_user_id(user_id)
        with self.conn.transaction():
            self.conn.execute("INSERT INTO users (discord_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
            row = self.conn.execute(
                "UPDATE users SET feed_token = %s WHERE discord_id = %s AND feed_token IS NULL RETURNING feed_token",
                (new_feed_token(), user_id),
            ).fetchone()
            if row is None:
                row = self.conn.execute("SELECT feed_token FROM users WHERE discord_id = %s", (user_id,)).fetchone()
            return row[0]

    def regenerate_feed_token(self, user_id: str) -> str:
        user_id = validate_user_id(user_id)
        with self.conn.transaction():
            self.conn.execute("INSERT INTO users (discord_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
            row = self.conn.execute(
                "UPDATE users SET feed_token = %s WHERE discord_id = %s RETURNING feed_token",
                (new_feed_token(), user_id),
            ).fetchone()
            return row[0]
