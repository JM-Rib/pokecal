"""Unit tests for configuration loading."""

from pokecal.config import load_config, create_default_config_if_missing


def test_create_and_load_config(tmp_path):
    cfg_file = tmp_path / "stores.yaml"
    create_default_config_if_missing(cfg_file)

    assert cfg_file.exists()
    config = load_config(cfg_file)

    assert config.calendar_name == "Pokémon TCG Events"
    assert config.ics_path == "dist/pokecal.ics"
    assert config.default_timezone == "Europe/Paris"
    assert len(config.stores) == 1
    store = config.stores[0]
    assert store.name == "Le coin des barons - Paris Rivoli"
    assert store.enabled is True
    assert "TCG" in store.filters.game_categories
