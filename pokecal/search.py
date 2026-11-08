"""Store search on the Play! Pokémon Event Locator (city -> nearby stores)."""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
from datetime import date
from typing import Any, Callable

from playwright.async_api import Page, async_playwright
from playwright_stealth import Stealth

from pokecal.models import SearchedStore
from pokecal.scraper import DEFAULT_USER_AGENT

logger = logging.getLogger(__name__)

BASE_URL = "https://events.pokemon.com/EventLocator"
LOCATIONS_ACTION = "DataActionGetLocations"


def build_search_url(
    latitude: float,
    longitude: float,
    range_: int = 25,
    is_km: bool = False,
    on_date: date | None = None,
    locale: str = "en-US",
) -> str:
    """Build the locator home URL for a coordinate-based store search."""
    params = [
        ("latitude", latitude),
        ("longitude", longitude),
        ("iskm", str(is_km).lower()),
        ("range", range_),
        ("SortDistance", "true"),
        ("locale", locale),
        ("startdate", (on_date or date.today()).isoformat()),
    ]
    return f"{BASE_URL}/Home?{urllib.parse.urlencode(params)}"


def build_location_detail_url(
    store: SearchedStore,
    range_: int = 25,
    is_km: bool = False,
    on_date: date | None = None,
    locale: str = "en-US",
) -> str:
    """Build a LocationDetail URL from a store's own GUID and coordinates."""
    params = [
        ("EventDetailGUID", ""),
        ("range", range_),
        ("latitude", store.latitude if store.latitude is not None else ""),
        ("startdate", (on_date or date.today()).isoformat()),
        ("LocationGuid", store.guid),
        ("storename", store.name),
        ("iskm", str(is_km).lower()),
        ("locale", locale),
        ("LocationName", store.name),
        ("longitude", store.longitude if store.longitude is not None else ""),
    ]
    return f"{BASE_URL}/LocationDetail?{urllib.parse.urlencode(params)}"


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_locations_response(payload: str) -> list[SearchedStore]:
    """Parse the body of the DataActionGetLocations response."""
    try:
        data = json.loads(payload)
        locations = data["data"]["Locations"]["List"]
    except (ValueError, KeyError, TypeError):
        logger.warning("Unexpected locations payload")
        return []

    stores: list[SearchedStore] = []
    for loc in locations:
        guid = (loc.get("Guid") or "").strip()
        name = (loc.get("Display_name") or "").strip()
        if not guid or not name:
            continue
        address = loc.get("Address") or {}
        stores.append(
            SearchedStore(
                guid=guid,
                name=name,
                address=(address.get("Full_address") or "").strip(),
                latitude=_to_float(address.get("Latitude")),
                longitude=_to_float(address.get("Longitude")),
            )
        )
    return stores


async def _open_search_page(page: Page, timeout_ms: int) -> None:
    await page.goto(f"{BASE_URL}/Home", wait_until="domcontentloaded", timeout=timeout_ms)
    await page.wait_for_selector(".el-reskin-layout", timeout=timeout_ms)
    try:
        await page.get_by_role("button", name="Accept All").click(timeout=3000)
    except Exception:
        logger.debug("No cookie banner to dismiss")


async def search_stores(
    city: str,
    choose_suggestion: Callable[[list[str]], int],
    headless: bool = False,
    timeout_ms: int = 40000,
) -> list[SearchedStore]:
    """Type a city, pick an autocomplete suggestion, return the nearby stores.

    The locator's bot protection blocks headless Chromium, so a visible
    browser is the default. `choose_suggestion` receives the suggestion labels
    and returns the index to select.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        try:
            context = await browser.new_context(
                user_agent=DEFAULT_USER_AGENT,
                locale="en-US",
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()
            await Stealth().apply_stealth_async(page)

            payloads: list[str] = []

            async def capture(response: Any) -> None:
                if LOCATIONS_ACTION in response.url:
                    payloads.append(await response.text())

            page.on("response", lambda r: asyncio.ensure_future(capture(r)))

            await _open_search_page(page, timeout_ms)
            field = page.locator("#b3-Input_LocationName")
            await field.click()
            await field.press_sequentially(city, delay=120)
            try:
                await page.wait_for_selector(".pac-item", timeout=10000)
            except Exception:
                return []

            labels: list[str] = await page.evaluate(
                "() => [...document.querySelectorAll('.pac-container .pac-item')]"
                ".map(e => [...e.querySelectorAll('span')].map(s => s.textContent.trim())"
                ".filter(Boolean).filter((t, i, a) => a.indexOf(t) === i).join(', '))"
            )
            index = choose_suggestion(labels)
            for _ in range(index + 1):
                await page.keyboard.press("ArrowDown")
            await page.keyboard.press("Enter")

            await page.wait_for_timeout(1000)
            for _ in range(int(timeout_ms / 500)):
                if payloads:
                    break
                await page.wait_for_timeout(500)
            return parse_locations_response(payloads[-1]) if payloads else []
        finally:
            await browser.close()
