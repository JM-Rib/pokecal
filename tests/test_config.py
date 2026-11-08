"""Unit tests for configuration loading."""

from pokecal.config import add_favorite_store, create_default_config_if_missing, load_config


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


def test_add_favorite_store_preserves_file_and_skips_duplicates(tmp_path):
    cfg_file = tmp_path / "stores.yaml"
    create_default_config_if_missing(cfg_file)
    original = cfg_file.read_text(encoding="utf-8")
    url = "https://events.pokemon.com/EventLocator/LocationDetail?LocationGuid=abc-123&storename=Shop"

    assert add_favorite_store(cfg_file, 'Shop "One"', url, "abc-123") is True
    assert add_favorite_store(cfg_file, "Shop again", url, "ABC-123") is False
    assert add_favorite_store(cfg_file, "Other", url.replace("abc-123", "def-456"), "def-456") is True

    text = cfg_file.read_text(encoding="utf-8")
    assert text.startswith(original.rstrip("\n"))
    config = load_config(cfg_file)
    assert [s.name for s in config.stores] == ["Le coin des barons - Paris Rivoli", 'Shop "One"', "Other"]
    assert config.default_timezone == "Europe/Paris"


def test_add_favorite_store_before_trailing_key_and_empty_list(tmp_path):
    url = "https://events.pokemon.com/EventLocator/LocationDetail?LocationGuid=abc-123"
    cfg_file = tmp_path / "stores.yaml"
    cfg_file.write_text("stores: []\noutput:\n  calendar_name: \"X\"\n", encoding="utf-8")

    assert add_favorite_store(cfg_file, "Shop", url, "abc-123") is True
    config = load_config(cfg_file)
    assert [s.name for s in config.stores] == ["Shop"]
    assert config.calendar_name == "X"

    missing = tmp_path / "new.yaml"
    assert add_favorite_store(missing, "Shop", url, "abc-123") is True
    assert len(load_config(missing).stores) == 1
