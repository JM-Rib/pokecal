"""Command Line Interface for PokéCal using Typer and Rich."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pokecal import __version__
from pokecal.calendar import export_ical_file
from pokecal.config import create_default_config_if_missing, load_config
from pokecal.parser import parse_store_url
from pokecal.scraper import PokemonScraper

app = typer.Typer(
    name="pokecal",
    help="PokéCal - Play! Pokémon TCG Event Sync (Open iCalendar / Webcal).",
    add_completion=False,
)
console = Console()


@app.command()
def sync(
    config_file: Path = typer.Option(
        Path("stores.yaml"),
        "--config",
        "-c",
        help="Path to stores.yaml configuration file.",
    ),
    output_path: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Custom output path for the .ics file (overrides config).",
    ),
    headless: bool = typer.Option(
        True,
        "--headless/--no-headless",
        help="Run browser in headless mode.",
    ),
) -> None:
    """Scrape configured stores and generate the .ics calendar feed."""
    console.print(Panel(f"[bold yellow]PokéCal[/bold yellow] [dim]v{__version__}[/dim]\nSyncing Play! Pokémon TCG events..."))

    if not config_file.exists():
        console.print(f"[yellow]Configuration file '{config_file}' not found. Generating default...[/yellow]")
        create_default_config_if_missing(config_file)

    config = load_config(config_file)
    active_stores = [s for s in config.stores if s.enabled]

    if not active_stores:
        console.print("[red]No active stores found in configuration.[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]Found {len(active_stores)} enabled store(s) to synchronize:[/green]")
    for st in active_stores:
        console.print(f"  • [bold]{st.name}[/bold]")

    scraper = PokemonScraper(headless=headless)
    with console.status("[bold cyan]Scraping events from Play! Pokémon...[/bold cyan]"):
        events = asyncio.run(scraper.scrape_stores(active_stores))

    if not events:
        console.print("[yellow]No matching events found across configured stores.[/yellow]")
    else:
        table = Table(title=f"Discovered Events ({len(events)})", header_style="bold magenta")
        table.add_column("Date & Time", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Event Title", style="bold white")
        table.add_column("Store / Venue", style="yellow")

        for ev in events:
            dt_display = ev.start_time.strftime("%a %b %d, %Y %H:%M")
            table.add_row(dt_display, ev.event_type, ev.title, ev.store_name)

        console.print(table)

    dest_path = output_path or Path(config.ics_path)
    export_ical_file(
        events=events,
        output_path=dest_path,
        calendar_name=config.calendar_name,
        calendar_description=config.calendar_description,
        default_timezone=config.default_timezone,
    )

    console.print(f"\n[bold green]✓ iCalendar feed successfully generated:[/bold green] [bold underline]{dest_path.resolve()}[/bold underline]")
    console.print("[dim]Subscribe in Google Calendar, Apple Calendar, or Outlook via URL or file import.[/dim]")


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
        from pokecal.models import StoreConfig
        fake_cfg = StoreConfig(name=meta.name, url=url, enabled=True)
        scraper = PokemonScraper(headless=headless)
        with console.status("[cyan]Running Playwright scraper...[/cyan]"):
            events = asyncio.run(scraper.scrape_store(fake_cfg))
        console.print(f"[green]Found {len(events)} events:[/green]")
        for ev in events:
            console.print(f"  • {ev.start_time.strftime('%Y-%m-%d %H:%M')}: [bold]{ev.title}[/bold] ({ev.event_type})")


@app.command()
def init(
    path: Path = typer.Option(Path("stores.yaml"), "--output", "-o", help="Target path for stores.yaml"),
) -> None:
    """Create a starter stores.yaml configuration."""
    out = create_default_config_if_missing(path)
    console.print(f"[bold green]Created starter configuration at:[/bold green] {out.resolve()}")


@app.command()
def version() -> None:
    """Show PokéCal version."""
    console.print(f"PokéCal v{__version__}")


if __name__ == "__main__":
    app()
