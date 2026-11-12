"""Command Line Interface for PokéCal using Typer and Rich."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional
import psycopg
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pokecal import __version__
from pokecal.calendar import export_ical_file
from pokecal.config import database_url, load_config
from pokecal.db import PostgresStoreRepository, StoreRepository, validate_user_id
from pokecal.models import PokemonEvent, StoreConfig
from pokecal.parser import parse_store_url
from pokecal.scraper import PokemonScraper
from pokecal.search import build_location_detail_url, search_stores
from pokecal.sync import sync_users

app = typer.Typer(
    name="pokecal",
    help="PokéCal - Play! Pokémon TCG Event Sync (Open iCalendar / Webcal).",
    add_completion=False,
)
console = Console()


def open_repository() -> StoreRepository:
    """Connect to Postgres or exit with a usage error."""
    try:
        return PostgresStoreRepository(database_url())
    except (ValueError, psycopg.Error) as exc:
        console.print(f"[red]Database unavailable: {exc}[/red]")
        raise typer.Exit(code=2)


@app.command()
def sync(
    users: Optional[list[str]] = typer.Option(
        None,
        "--user",
        "-u",
        help="Discord user ID to sync (repeatable). Defaults to all users.",
    ),
    headless: bool = typer.Option(
        True,
        "--headless/--no-headless",
        help="Run browser in headless mode.",
    ),
) -> None:
    """Scrape each user's enabled stores and write one .ics feed per user."""
    console.print(Panel(f"[bold yellow]PokéCal[/bold yellow] [dim]v{__version__}[/dim]\nSyncing Play! Pokémon TCG events..."))

    config = load_config()
    repo = open_repository()
    known = repo.list_users()

    if users:
        try:
            targets = list(dict.fromkeys(validate_user_id(u) for u in users))
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=2)
        unknown = [u for u in targets if u not in known]
        if unknown:
            console.print(f"[red]Unknown user(s): {', '.join(unknown)}[/red]")
            raise typer.Exit(code=2)
    else:
        targets = known

    if not targets:
        console.print("[yellow]No users with saved stores.[/yellow]")
        return

    scraper = PokemonScraper(headless=headless)

    def export(user_id: str, events: list[PokemonEvent]) -> None:
        dest = Path(config.output_dir) / f"{repo.get_feed_token(user_id)}.ics"
        export_ical_file(
            events=events,
            output_path=dest,
            calendar_name=config.calendar_name,
            calendar_description=config.calendar_description,
            default_timezone=config.default_timezone,
        )
        console.print(f"[green]✓[/green] {len(events)} event(s) → [underline]{dest.resolve()}[/underline]")

    result = sync_users(
        repo,
        targets,
        scrape=lambda stores: asyncio.run(scraper.scrape_stores(stores)),
        export=export,
    )

    for i, error in enumerate(result.failed.values(), 1):
        console.print(f"[red]✗ failed feed {i}: {error}[/red]")
    if result.failed:
        raise typer.Exit(code=1)


@app.command()
def regenerate_token(
    user: str = typer.Option(..., "--user", "-u", help="Discord user ID whose feed token to replace."),
) -> None:
    """Replace a user's feed token; the old feed URL stops being updated."""
    try:
        user = validate_user_id(user)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2)
    repo = open_repository()
    old = repo.get_feed_token(user)
    new = repo.regenerate_feed_token(user)
    (Path(load_config().output_dir) / f"{old}.ics").unlink(missing_ok=True)
    console.print(f"[green]✓[/green] New feed file name: {new}.ics (run `pokecal sync` to publish it)")


@app.command()
def inspect_store(
    url: str = typer.Argument(..., help="Official events.pokemon.com LocationDetail URL."),
    fetch_events: bool = typer.Option(
        False,
        "--fetch",
        "-f",
        help="Also fetch live events from the page.",
    ),
    headless: bool = typer.Option(
        True,
        "--headless/--no-headless",
        help="Run browser in headless mode if fetching.",
    ),
) -> None:
    """Parse and inspect metadata from a store URL."""
    meta = parse_store_url(url)

    table = Table(title="Store Metadata", header_style="bold blue")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Store Name", meta.name)
    table.add_row("Location GUID", meta.location_guid or "[dim](not specified)[/dim]")
    table.add_row("Latitude", str(meta.latitude))
    table.add_row("Longitude", str(meta.longitude))
    table.add_row("Detected Timezone", f"[bold]{meta.timezone}[/bold]")
    table.add_row("Locale", meta.locale)

    console.print(table)

    if fetch_events:
        console.print("\n[bold cyan]Fetching live events for this venue...[/bold cyan]")
        fake_cfg = StoreConfig(name=meta.name, url=url, enabled=True)
        scraper = PokemonScraper(headless=headless)
        with console.status("[cyan]Running Playwright scraper...[/cyan]"):
            events = asyncio.run(scraper.scrape_store(fake_cfg))
        console.print(f"[green]Found {len(events)} events:[/green]")
        for ev in events:
            console.print(f"  • {ev.start_time.strftime('%Y-%m-%d %H:%M')}: [bold]{ev.title}[/bold] ({ev.event_type})")


@app.command()
def search(
    city: str = typer.Argument(..., help="City to search around."),
    user: str = typer.Option(..., "--user", "-u", help="Discord user ID that owns the favorites."),
    range_: int = typer.Option(25, "--range", "-r", help="Search radius."),
    km: bool = typer.Option(False, "--km", help="Use kilometres instead of miles."),
    headless: bool = typer.Option(
        False,
        "--headless/--no-headless",
        help="The locator blocks headless browsers, so a visible window is the default.",
    ),
) -> None:
    """Search stores near a city and save favorites for a Discord user."""

    try:
        user = validate_user_id(user)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=2)
    repo = open_repository()

    def choose(labels: list[str]) -> int:
        for i, label in enumerate(labels, 1):
            console.print(f"  [cyan]{i}[/cyan]. {label}")
        return typer.prompt("Pick a town", type=typer.IntRange(1, len(labels))) - 1

    stores = asyncio.run(search_stores(city, choose, headless=headless))

    if not stores:
        console.print(f"[yellow]No town or store found for '{city}'.[/yellow]")
        raise typer.Exit(code=1)

    table = Table(title=f"Stores ({len(stores)})", header_style="bold magenta")
    table.add_column("#", style="cyan")
    table.add_column("Store", style="bold white")
    table.add_column("Address", style="yellow")
    for i, st in enumerate(stores, 1):
        table.add_row(str(i), st.name, st.address)
    console.print(table)

    answer = typer.prompt("Favorites to save (comma-separated numbers, empty to skip)", default="", show_default=False)
    picks = {int(x) for x in answer.replace(" ", "").split(",") if x.isdigit()}
    for i in sorted(picks):
        if not 1 <= i <= len(stores):
            console.print(f"[red]Ignoring invalid number {i}.[/red]")
            continue
        st = stores[i - 1]
        url = build_location_detail_url(st, range_=range_, is_km=km)
        if repo.add_favorite(user, StoreConfig(name=st.name, url=url), st.guid):
            console.print(f"[green]✓ Saved[/green] {st.name}")
        else:
            console.print(f"[yellow]Already configured:[/yellow] {st.name}")


@app.command()
def version() -> None:
    """Show PokéCal version."""
    console.print(f"PokéCal v{__version__}")


if __name__ == "__main__":
    app()
