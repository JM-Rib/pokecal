"""Unit tests for store URL parsing and timezone resolution."""

from pokecal.parser import parse_store_url


def test_parse_store_url():
    url = (
        "https://events.pokemon.com/EventLocator/LocationDetail?"
        "EventDetailGUID=&range=25&latitude=48.8575475&startdate=2026-11-07"
        "&LocationGuid=d31263f1-80fb-0a60-8b04-72c8887c24f2"
        "&storename=LE+COIN+DES+BARONS+-+PARIS+RIVOLI&iskm=false&locale=fr-FR"
        "&LocationName=LE+COIN+DES+BARONS+-+PARIS+RIVOLI&longitude=2.3513765"
    )
    meta = parse_store_url(url)

    assert meta.location_guid == "d31263f1-80fb-0a60-8b04-72c8887c24f2"
    assert meta.name == "LE COIN DES BARONS - PARIS RIVOLI"
    assert meta.latitude == 48.8575475
    assert meta.longitude == 2.3513765
    assert meta.locale == "fr-FR"
    # Paris, France coordinates must resolve to Europe/Paris
    assert meta.timezone == "Europe/Paris"


def test_parse_store_url_with_missing_coords():
    url = "https://events.pokemon.com/EventLocator/LocationDetail?LocationGuid=abc-123&storename=Test+Shop"
    meta = parse_store_url(url, default_timezone="America/New_York")

    assert meta.location_guid == "abc-123"
    assert meta.name == "Test Shop"
    assert meta.latitude is None
    assert meta.longitude is None
    assert meta.timezone == "America/New_York"
