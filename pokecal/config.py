"""Environment-based configuration for PokéCal."""

from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import quote

from pokecal.models import PokéCalConfig


def load_config(env: Mapping[str, str] | None = None) -> PokéCalConfig:
    """Build output settings from POKECAL_* environment variables."""
    env = os.environ if env is None else env
    defaults = PokéCalConfig()
    return PokéCalConfig(
        calendar_name=env.get("POKECAL_CALENDAR_NAME", defaults.calendar_name),
        calendar_description=env.get("POKECAL_CALENDAR_DESCRIPTION", defaults.calendar_description),
        output_dir=env.get("POKECAL_OUTPUT_DIR", defaults.output_dir),
        default_timezone=env.get("POKECAL_DEFAULT_TIMEZONE", defaults.default_timezone),
    )


def database_url(env: Mapping[str, str] | None = None) -> str:
    """Return the Postgres connection URL.

    Uses DATABASE_URL when set, otherwise builds one from the POSTGRES_* variables
    shared with docker-compose.yml (POSTGRES_HOST defaults to localhost).
    """
    env = os.environ if env is None else env
    if env.get("DATABASE_URL"):
        return env["DATABASE_URL"]
    password = env.get("POSTGRES_PASSWORD")
    if not password:
        raise ValueError("Set DATABASE_URL or POSTGRES_PASSWORD (see .env.example).")
    user = quote(env.get("POSTGRES_USER", "pokecal"), safe="")
    host = env.get("POSTGRES_HOST", "localhost")
    port = env.get("POSTGRES_PORT", "5432")
    db = quote(env.get("POSTGRES_DB", "pokecal"), safe="")
    return f"postgresql://{user}:{quote(password, safe='')}@{host}:{port}/{db}"
