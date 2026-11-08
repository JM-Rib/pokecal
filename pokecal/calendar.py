"""RFC 5545 iCalendar generation using icalendar."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Sequence
import pytz
import icalendar
from pokecal.models import PokemonEvent

logger = logging.getLogger(__name__)

PRODID = "-//PokéCal//Play Pokémon TCG Calendar//EN"


def create_calendar(
    name: str = "Pokémon TCG Events",
    description: str = "Pokémon TCG Tournaments synchronized by PokéCal",
    default_timezone: str = "Europe/Paris",
) -> icalendar.Calendar:
    """Create and configure a base RFC 5545 iCalendar object."""
    cal = icalendar.Calendar()
    cal.add("prodid", PRODID)
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", name)
    cal.add("x-wr-caldesc", description)
    cal.add("x-wr-timezone", default_timezone)
    cal.add("x-published-ttl", "PT6H")
    cal.add("refresh-interval;value=duration", "PT6H")
    return cal


def format_event_summary(event: PokemonEvent) -> str:
    """Format an informative and attractive summary/title for the calendar event."""
    # Prefix with appropriate emoji
    t_lower = (event.title + " " + event.event_type).lower()
    if "cup" in t_lower or "coupe" in t_lower:
        badge = "🏆"
    elif "challenge" in t_lower or "défi" in t_lower:
        badge = "🥇"
    elif "prerelease" in t_lower or "avant-première" in t_lower:
        badge = "🎁"
    elif "league" in t_lower or "ligue" in t_lower:
        badge = "🎴"
    else:
        badge = "⚔️"

    category = event.game_category or "TCG"
    return f"{badge} {event.title} - {event.store_name} ({category})"


def format_event_description(event: PokemonEvent) -> str:
    """Build a detailed and formatted description for the calendar event."""
    lines: list[str] = []

    if event.event_type:
        lines.append(f"🎯 Event Type: {event.event_type}")
    if event.format:
        lines.append(f"🃏 Format: {event.format}")
    if event.cost:
        lines.append(f"💰 Entry Fee: {event.cost}")
    if event.registration_info:
        lines.append(f"📝 Registration: {event.registration_info}")

    venue_parts = [p for p in [event.location_name or event.store_name, event.location_address] if p]
    if venue_parts:
        lines.append(f"📍 Location: {', '.join(venue_parts)}")

    if event.description and event.description.strip():
        lines.append("")
        lines.append(event.description.strip())

    if event.url:
        lines.append("")
        lines.append(f"🔗 Official Pokémon Event Page:\n{event.url}")

    lines.append("")
    lines.append("⚡ Synced automatically by PokéCal (Open iCalendar / Webcal)")

    return "\n".join(lines)


def event_to_vevent(event: PokemonEvent, created_at: datetime | None = None) -> icalendar.Event:
    """Convert a PokemonEvent into an RFC 5545 VEVENT component."""
    vevent = icalendar.Event()

    uid = event.get_uid()
    vevent.add("uid", uid)

    stamp = created_at or datetime.now(pytz.utc)
    if stamp.tzinfo is None:
        stamp = pytz.utc.localize(stamp)
    vevent.add("dtstamp", stamp)

    # Resolve event timezone
    try:
        tz = pytz.timezone(event.timezone)
    except Exception:
        tz = pytz.timezone("Europe/Paris")

    # Ensure start_time is timezone-aware
    start_dt = event.start_time
    if start_dt.tzinfo is None:
        start_dt = tz.localize(start_dt)
    else:
        start_dt = start_dt.astimezone(tz)

    end_dt = event.effective_end_time()
    if end_dt.tzinfo is None:
        end_dt = tz.localize(end_dt)
    else:
        end_dt = end_dt.astimezone(tz)

    vevent.add("dtstart", start_dt)
    vevent.add("dtend", end_dt)

    summary = format_event_summary(event)
    vevent.add("summary", summary)

    description = format_event_description(event)
    vevent.add("description", description)

    location_str = ", ".join(
        p for p in [event.location_name or event.store_name, event.location_address] if p
    )
    if location_str:
        vevent.add("location", location_str)

    if event.url:
        vevent.add("url", event.url)

    status = (event.status or "CONFIRMED").upper()
    if status not in {"CONFIRMED", "CANCELLED", "TENTATIVE"}:
        status = "CONFIRMED"
    vevent.add("status", status)

    categories = ["Pokemon", event.game_category or "TCG"]
    if event.event_type and event.event_type not in categories:
        categories.append(event.event_type)
    vevent.add("categories", categories)

    vevent.add("transp", "OPAQUE")
    vevent.add("sequence", 0)

    return vevent


def generate_ical_feed(
    events: Sequence[PokemonEvent],
    calendar_name: str = "Pokémon TCG Events",
    calendar_description: str = "Pokémon TCG Tournaments synchronized by PokéCal",
    default_timezone: str = "Europe/Paris",
) -> bytes:
    """Generate RFC 5545 iCalendar binary data for a collection of events."""
    cal = create_calendar(
        name=calendar_name,
        description=calendar_description,
        default_timezone=default_timezone,
    )

    now_utc = datetime.now(pytz.utc)

    # Sort events chronologically
    sorted_events = sorted(events, key=lambda e: e.start_time)

    for ev in sorted_events:
        vevent = event_to_vevent(ev, created_at=now_utc)
        cal.add_component(vevent)

    return cal.to_ical()


def export_ical_file(
    events: Sequence[PokemonEvent],
    output_path: str | Path,
    calendar_name: str = "Pokémon TCG Events",
    calendar_description: str = "Pokémon TCG Tournaments synchronized by PokéCal",
    default_timezone: str = "Europe/Paris",
) -> Path:
    """Generate and write an .ics file to the specified path."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    ical_bytes = generate_ical_feed(
        events=events,
        calendar_name=calendar_name,
        calendar_description=calendar_description,
        default_timezone=default_timezone,
    )

    out.write_bytes(ical_bytes)
    logger.info("Successfully exported %d events to %s", len(events), out.resolve())
    return out
