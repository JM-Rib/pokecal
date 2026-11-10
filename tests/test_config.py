"""Unit tests for environment-based configuration."""

import pytest

from pokecal.config import database_url, load_config


def test_load_config_defaults_and_overrides():
    assert load_config({}).output_dir == "dist"
    config = load_config({"POKECAL_OUTPUT_DIR": "out", "POKECAL_DEFAULT_TIMEZONE": "UTC"})
    assert config.output_dir == "out"
    assert config.default_timezone == "UTC"


def test_database_url_prefers_database_url_then_postgres_vars():
    assert database_url({"DATABASE_URL": "postgresql://x/y", "POSTGRES_PASSWORD": "p"}) == "postgresql://x/y"
    url = database_url({"POSTGRES_PASSWORD": "p@ss", "POSTGRES_HOST": "db"})
    assert url == "postgresql://pokecal:p%40ss@db:5432/pokecal"


def test_database_url_requires_credentials():
    with pytest.raises(ValueError):
        database_url({})
