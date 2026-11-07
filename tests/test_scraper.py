"""Unit tests for card parsing logic."""

from datetime import datetime
import pytz
from pokecal.models import StoreMetadata
from pokecal.scraper import parse_event_card_data


def test_parse_event_card_data_french():
    store_meta = StoreMetadata(
        location_guid="d31263f1-80fb-0a60-8b04-72c8887c24f2",
        name="LE COIN DES BARONS - PARIS RIVOLI",
        latitude=48.8575,
        longitude=2.3513,
        timezone="Europe/Paris",
        address="48B RUE DE RIVOLI, 75004 PARIS, FRANCE",
    )

    raw_card = {
        "ariaLabel": (
            "Type de l’évènement : Challenge de Ligue Nom de l’évènement : LCDB - RIVOLI - League Challenge Nov.\r\n"
            "Lieu de l’évènement : 48B RUE DE RIVOLI, 75004 PARIS, FRANCEDate de l’évènement : Nov 08, 2026 19:00\r\n"
            "Produit :  JCC"
        ),
        "category": "Challenge de Ligue",
        "title": "LCDB - RIVOLI - League Challenge Nov.",
        "location": "48B RUE DE RIVOLI, 75004 PARIS, FRANCED",
        "dateText": "samedi, 08 novembre 2026 07:00 PM",
        "isTcg": True,
    }

    event = parse_event_card_data(raw_card, store_meta)
    assert event is not None
    assert event.title == "LCDB - RIVOLI - League Challenge Nov."
    assert event.event_type == "Challenge de Ligue"
    assert event.game_category == "TCG"
    assert event.store_guid == "d31263f1-80fb-0a60-8b04-72c8887c24f2"
    assert event.store_name == "LE COIN DES BARONS - PARIS RIVOLI"
    assert event.start_time.year == 2026
    assert event.start_time.month == 11
    assert event.start_time.day == 8
    assert event.start_time.hour == 19
    assert event.start_time.minute == 0
    assert str(event.start_time.tzinfo) == "Europe/Paris"


def test_parse_event_card_ignores_store_banner():
    store_meta = StoreMetadata(
        location_guid="123",
        name="Test Shop",
        timezone="Europe/Paris",
    )

    raw_card = {
        "ariaLabel": "Magasin de jeux : Test Shop",
        "category": "Magasin de jeux",
        "title": "Test Shop",
        "location": "Paris",
        "dateText": "",
        "isTcg": False,
    }

    event = parse_event_card_data(raw_card, store_meta)
    assert event is None
