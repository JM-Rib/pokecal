"""Discord client wiring (discord.py slash commands) around `pokecal.bot.BotService`.

No `from __future__ import annotations` here: discord.py reads the command signatures at runtime.
"""

import asyncio
import logging
from typing import Any

from pokecal.bot import BotError, BotService
from pokecal.db import StoreRepository
from pokecal.search import search_stores

logger = logging.getLogger(__name__)

MAX_CHOICES = 25


def run_bot(token: str, repo: StoreRepository, headless: bool = False) -> None:
    """Start the bot and block until it stops. Requires the `discord.py` package."""
    try:
        import discord
        from discord import app_commands
    except ImportError as exc:
        raise RuntimeError("discord.py is not installed; add it with `uv add discord.py`.") from exc

    # One visible browser at a time: the locator blocks headless browsers.
    search_lock = asyncio.Lock()

    async def search(city: str):
        async with search_lock:
            return await search_stores(city, lambda labels: 0, headless=headless)

    service = BotService(repo, search)
    client = discord.Client(intents=discord.Intents.default())
    tree = app_commands.CommandTree(client)

    async def respond(interaction: discord.Interaction, action: Any, *args: Any, **kwargs: Any) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            result = action(*args, **kwargs)
            message = await result if asyncio.iscoroutine(result) else result
        except BotError as exc:
            message = str(exc)
        except Exception:
            logger.exception("Command failed")
            message = "Something went wrong, please try again later."
        await interaction.followup.send(message[:2000], ephemeral=True)

    def choices(names: list[str], current: str) -> list[app_commands.Choice[str]]:
        needle = current.lower()
        return [app_commands.Choice(name=n[:100], value=n[:100]) for n in names if needle in n.lower()][:MAX_CHOICES]

    async def result_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return choices(service.result_names(str(interaction.user.id)), current)

    async def favorite_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        names = await asyncio.to_thread(service.favorite_names, str(interaction.user.id))
        return choices(names, current)

    @tree.command(name="search", description="Find Pokémon TCG stores near a city")
    @app_commands.describe(city="City to search around")
    async def search_command(interaction: discord.Interaction, city: str) -> None:
        await respond(interaction, service.search, str(interaction.user.id), city)

    @tree.command(name="add", description="Add a store from your last search to your favorites")
    @app_commands.describe(store="Store name or its number in the search results")
    @app_commands.autocomplete(store=result_autocomplete)
    async def add_command(interaction: discord.Interaction, store: str) -> None:
        await respond(interaction, asyncio.to_thread, service.add, str(interaction.user.id), store)

    @tree.command(name="remove", description="Remove a store from your favorites")
    @app_commands.describe(store="Store name or its number in /list")
    @app_commands.autocomplete(store=favorite_autocomplete)
    async def remove_command(interaction: discord.Interaction, store: str) -> None:
        await respond(interaction, asyncio.to_thread, service.remove, str(interaction.user.id), store)

    @tree.command(name="list", description="Show your favorite stores and their filters")
    async def list_command(interaction: discord.Interaction) -> None:
        await respond(interaction, asyncio.to_thread, service.list, str(interaction.user.id))

    @tree.command(name="filter", description="Choose which events you see from a favorite store")
    @app_commands.describe(
        store="Store name or its number in /list",
        event_types="Comma-separated event types, e.g. League, Cup (or 'any')",
        game_categories="Comma-separated games: TCG, VGC, GO (or 'any')",
        exclude_keywords="Comma-separated words to hide (or 'none')",
        enabled="Include this store in your calendar",
    )
    @app_commands.autocomplete(store=favorite_autocomplete)
    async def filter_command(
        interaction: discord.Interaction,
        store: str,
        event_types: str | None = None,
        game_categories: str | None = None,
        exclude_keywords: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        await respond(
            interaction,
            asyncio.to_thread,
            lambda: service.filter(
                str(interaction.user.id), store, event_types, game_categories, exclude_keywords, enabled
            ),
        )

    @client.event
    async def on_ready() -> None:
        await tree.sync()
        logger.info("Bot ready as %s", client.user)

    client.run(token)
