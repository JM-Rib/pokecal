"""Configuration management for PokéCal (stores.yaml)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any
import yaml
from pokecal.models import PokéCalConfig, StoreConfig, StoreFilterConfig

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = "stores.yaml"

DEFAULT_STORES_YAML = """# PokéCal Stores Configuration
output:
  ics_path: "dist/pokecal.ics"
  calendar_name: "Pokémon TCG Events"
  calendar_description: "Pokémon TCG Tournaments synchronized by PokéCal"
  default_timezone: "Europe/Paris"

stores:
  - name: "Le coin des barons - Paris Rivoli"
    url: "https://events.pokemon.com/EventLocator/LocationDetail?EventDetailGUID=&range=25&latitude=48.8575475&startdate=2026-11-07&LocationGuid=d31263f1-80fb-0a60-8b04-72c8887c24f2&storename=LE+COIN+DES+BARONS+-+PARIS+RIVOLI&iskm=false&locale=fr-FR&LocationName=LE+COIN+DES+BARONS+-+PARIS+RIVOLI&longitude=2.3513765"
    enabled: true
    filters:
      game_categories:
        - "TCG"
"""


def load_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> PokéCalConfig:
    """Load configuration from a YAML file.

    If file doesn't exist, returns a default configuration.
    """
    path = Path(config_path)
    if not path.exists():
        logger.warning("Config file %s not found. Using defaults.", path)
        return PokéCalConfig()

    with open(path, "r", encoding="utf-8") as f:
        raw_data: dict[str, Any] = yaml.safe_load(f) or {}

    output_opts = raw_data.get("output", {})
    calendar_name = output_opts.get("calendar_name", raw_data.get("calendar_name", "Pokémon TCG Events"))
    calendar_description = output_opts.get(
        "calendar_description",
        raw_data.get("calendar_description", "Pokémon TCG Tournaments synchronized by PokéCal"),
    )
    ics_path = output_opts.get("ics_path", raw_data.get("ics_path", "dist/pokecal.ics"))
    default_timezone = output_opts.get(
        "default_timezone",
        raw_data.get("default_timezone", "Europe/Paris"),
    )

    raw_stores = raw_data.get("stores", [])
    stores: list[StoreConfig] = []
    for s in raw_stores:
        filters_data = s.get("filters", {})
        filters = StoreFilterConfig(
            game_categories=filters_data.get("game_categories", ["TCG"]),
            event_types=filters_data.get("event_types"),
            exclude_keywords=filters_data.get("exclude_keywords", []),
        )
        stores.append(
            StoreConfig(
                name=s.get("name", "Store"),
                url=s.get("url", ""),
                enabled=s.get("enabled", True),
                filters=filters,
            )
        )

    return PokéCalConfig(
        calendar_name=calendar_name,
        calendar_description=calendar_description,
        ics_path=ics_path,
        default_timezone=default_timezone,
        stores=stores,
    )


def add_favorite_store(
    config_path: str | Path,
    name: str,
    url: str,
    location_guid: str,
) -> bool:
    """Append a favorite store to stores.yaml, leaving the rest of the file untouched.

    Returns False if a store with the same LocationGuid is already configured.
    """
    path = Path(config_path)
    text = path.read_text(encoding="utf-8") if path.exists() else DEFAULT_STORES_YAML.split("stores:")[0]
    data: dict[str, Any] = yaml.safe_load(text) or {}

    for existing in data.get("stores") or []:
        existing_url = (existing or {}).get("url", "")
        if location_guid.lower() in existing_url.lower():
            return False

    # JSON strings are valid YAML double-quoted scalars
    entry = (
        f"  - name: {json.dumps(name, ensure_ascii=False)}\n"
        f"    url: {json.dumps(url)}\n"
        "    enabled: true\n"
        "    filters:\n"
        "      game_categories:\n"
        '        - "TCG"\n'
    )

    lines = text.splitlines(keepends=True)
    start = next((i for i, ln in enumerate(lines) if re.match(r"stores:\s*(\[\s*\])?\s*(#.*)?$", ln)), None)
    if start is None:
        new_text = text.rstrip("\n") + "\n\nstores:\n" + entry
    else:
        # The stores block ends at the next top-level key or at EOF
        end = next(
            (i for i in range(start + 1, len(lines)) if re.match(r"\S", lines[i]) and not lines[i].startswith("#")),
            len(lines),
        )
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        lines[start] = "stores:\n"
        if lines[end - 1][-1:] != "\n":
            lines[end - 1] += "\n"
        lines.insert(end, entry)
        new_text = "".join(lines)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")
    return True


def create_default_config_if_missing(config_path: str | Path = DEFAULT_CONFIG_PATH) -> Path:
    """Create a default stores.yaml file if it does not already exist."""
    path = Path(config_path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_STORES_YAML, encoding="utf-8")
        logger.info("Created template configuration at %s", path)
    return path
