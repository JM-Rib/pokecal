"""Unit tests for RFC 5545 iCalendar generation."""

from datetime import datetime
import pytz
import icalendar
from pokecal.calendar import generate_ical_feed, export_ical_file
from pokecal.models import PokemonEvent


def test_generate_ical_feed():
    tz = pytz.timezone("Europe/Paris")
    event = PokemonEvent(
        guid="test-guid-9999",
        store_guid="store-1234",
        store_name="Le coin des barons - Paris Rivoli",
        title="League Challenge",
        game_category="TCG",
        event_type="League Challenge",
        format="Standard",
        start_time=tz.localize(datetime(2026, 11, 7, 14, 0, 0)),
        end_time=tz.localize(datetime(2026, 11, 7, 18, 0, 0)),
        timezone="Europe/Paris",
        cost="12.00 €",
        registration_info="On-site",
        url="https://events.pokemon.com/EventLocator/LocationDetail?EventDetailGUID=test-guid-9999",
        location_name="Le coin des barons - Paris Rivoli",
        location_address="Paris, France",
    )

    feed_bytes = generate_ical_feed([event], calendar_name="Pokémon TCG - Le coin des barons - Paris Rivoli")
    text = feed_bytes.decode("utf-8")

    assert "BEGIN:VCALENDAR" in text
    assert "VERSION:2.0" in text
    assert "X-WR-CALNAME:Pokémon TCG - Le coin des barons - Paris Rivoli" in text
    assert "BEGIN:VEVENT" in text
    assert "UID:pokemon-event-test-guid-9999@pokecal" in text
    assert "DTSTART;TZID=Europe/Paris:20261107T140000" in text
    assert "DTEND;TZID=Europe/Paris:20261107T180000" in text
    assert "STATUS:CONFIRMED" in text
    assert "END:VEVENT" in text
    assert "END:VCALENDAR" in text

    # Parse back with icalendar parser to ensure validity
    parsed_cal = icalendar.Calendar.from_ical(feed_bytes)
    events = [c for c in parsed_cal.walk() if c.name == "VEVENT"]
    assert len(events) == 1
    assert str(events[0]["uid"]) == "pokemon-event-test-guid-9999@pokecal"
    assert str(events[0]["summary"]) == "🥇 League Challenge - Le coin des barons - Paris Rivoli (TCG)"
    assert str(events[0]["location"]) == "Le coin des barons - Paris Rivoli, Paris, France"
    assert str(events[0]["status"]) == "CONFIRMED"


def test_export_ical_file(tmp_path):
    tz = pytz.timezone("Europe/Paris")
    event = PokemonEvent(
        guid="ev-1",
        store_guid="store-1",
        store_name="Shop",
        title="Weekly League",
        start_time=tz.localize(datetime(2026, 11, 14, 15, 0, 0)),
        timezone="Europe/Paris",
    )
    dest = tmp_path / "events.ics"
    exported_path = export_ical_file([event], dest)

    assert exported_path.exists()
    content = exported_path.read_text(encoding="utf-8")
    assert "Weekly League" in content
    assert "DTSTART;TZID=Europe/Paris:20261114T150000" in content
