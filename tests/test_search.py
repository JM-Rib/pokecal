"""Unit tests for store search URL building and result parsing."""

import json
from datetime import date

from pokecal.models import SearchedStore
from pokecal.parser import parse_store_url
from pokecal.search import build_location_detail_url, build_search_url, parse_locations_response

LOCATIONS_PAYLOAD = json.dumps(
    {
        "versionInfo": {"hasModuleVersionChanged": False},
        "data": {
            "Locations": {
                "List": [
                    {
                        "Guid": "35411d60-185f-4778-8e63-289315cf3020",
                        "Display_id": "L26100057",
                        "Group_type": "league",
                        "Display_name": "CARD'ERA SARL",
                        "Address": {
                            "Name": "CARD'ERA SARL",
                            "Full_address": "8 RUE DE FLEURIEU, LYON, AUVERGNE-RHÔNE-ALPES 69002, FR",
                            "Latitude": "45.753224",
                            "Longitude": "4.832489",
                        },
                    },
                    {
                        "Guid": "no-coords",
                        "Display_name": "NO COORDS",
                        "Address": {"Full_address": "SOMEWHERE", "Latitude": "", "Longitude": ""},
                    },
                    {"Guid": "", "Display_name": "MISSING GUID", "Address": {}},
                ]
            }
        },
    }
)


def test_build_search_url_matches_locator_format():
    url = build_search_url(48.8575475, 2.3513765, on_date=date(2026, 11, 8))
    assert url == (
        "https://events.pokemon.com/EventLocator/Home?latitude=48.8575475&longitude=2.3513765"
        "&iskm=false&range=25&SortDistance=true&locale=en-US&startdate=2026-11-08"
    )


def test_build_search_url_defaults_to_today_and_km_flag():
    url = build_search_url(1.0, 2.0, is_km=True, range_=50)
    assert "iskm=true" in url
    assert "range=50" in url
    assert f"startdate={date.today().isoformat()}" in url


def test_parse_locations_response():
    stores = parse_locations_response(LOCATIONS_PAYLOAD)

    assert [s.name for s in stores] == ["CARD'ERA SARL", "NO COORDS"]
    assert stores[0].guid == "35411d60-185f-4778-8e63-289315cf3020"
    assert stores[0].latitude == 45.753224
    assert stores[0].longitude == 4.832489
    assert stores[1].latitude is None


def test_parse_locations_response_invalid_or_empty():
    assert parse_locations_response("not json") == []
    assert parse_locations_response('{"data": {}}') == []
    assert parse_locations_response('{"data": {"Locations": {"List": []}}}') == []


def test_location_detail_url_keeps_store_own_coordinates():
    store = SearchedStore(
        guid="35411d60-185f-4778-8e63-289315cf3020",
        name="CARD'ERA SARL",
        latitude=45.753224,
        longitude=4.832489,
    )
    url = build_location_detail_url(store, on_date=date(2026, 11, 8))
    meta = parse_store_url(url)

    assert meta.location_guid == store.guid
    assert meta.name == "CARD'ERA SARL"
    assert meta.latitude == 45.753224
    assert meta.longitude == 4.832489
    assert meta.timezone == "Europe/Paris"
