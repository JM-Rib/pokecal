"""Playwright scraper for OutSystems-based Play! Pokémon Event Locator."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Sequence
import dateparser
import pytz
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from pokecal.models import PokemonEvent, StoreConfig, StoreFilterConfig, StoreMetadata
from pokecal.parser import parse_store_url

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def parse_event_card_data(
    raw: dict[str, Any],
    store_meta: StoreMetadata,
) -> PokemonEvent | None:
    """Parse raw DOM card data into a normalized PokemonEvent."""
    aria_label = raw.get("ariaLabel", "") or ""
    dom_category = (raw.get("category") or "").strip()
    dom_title = (raw.get("title") or "").strip()
    dom_location = (raw.get("location") or "").strip()
    dom_date_text = (raw.get("dateText") or "").strip()
    is_tcg = raw.get("isTcg", True)

    # Exclude venue store card
    if dom_category.lower() in {"magasin de jeux", "game store", "store"} and not dom_date_text:
        return None

    # Parse fields from aria-label with regex, supporting French and English variants
    # Sample ariaLabel:
    # "Type de l’évènement : Challenge de Ligue Nom de l’évènement : LCDB - RIVOLI - League Challenge Nov.\r\nLieu de l’évènement : 48B RUE DE RIVOLI, 75004 PARIS, FRANCEDate de l’évènement : Nov 08, 2026 19:00\r\nProduit :  JCC"
    type_match = re.search(r"(?:Type de l’évènement|Event Type)\s*:\s*([^N\r\n]+?)(?=\s*(?:Nom|Event|$))", aria_label, re.IGNORECASE)
    title_match = re.search(r"(?:Nom de l’évènement|Event Name)\s*:\s*([^L\r\n]+?)(?=\s*(?:Lieu|Location|Date|$))", aria_label, re.IGNORECASE)
    loc_match = re.search(r"(?:Lieu de l’évènement|Event Location)\s*:\s*([^D\r\n]+?)(?=\s*(?:Date|$))", aria_label, re.IGNORECASE)
    date_match = re.search(
        r"(?:Date de l’évènement|Event Date)\s*:\s*([A-Za-z]+\s+\d+,\s+\d{4}\s+\d{1,2}:\d{2})",
        aria_label,
        re.IGNORECASE,
    )
    prod_match = re.search(r"(?:Produit|Product)\s*:\s*([^\r\n]+)", aria_label, re.IGNORECASE)

    event_type = (type_match.group(1).strip() if type_match else dom_category) or "Tournament"
    raw_title = (title_match.group(1).strip() if title_match else dom_title)
    
    # If title is blank, or just the store name itself, provide an informative title based on event type
    if not raw_title or raw_title.lower() == store_meta.name.lower():
        if event_type.lower() in {"ligue", "league"}:
            title = "Ligue Pokémon"
        elif event_type.lower() in {"tournoi amical", "friendly tournament", "casual tournament"}:
            title = "Tournoi Amical"
        else:
            title = event_type
    else:
        title = raw_title
    location = (loc_match.group(1).strip() if loc_match else dom_location) or store_meta.address or store_meta.name
    product_str = prod_match.group(1).strip().upper() if prod_match else ""

    if "JCC" in product_str or "TCG" in product_str or is_tcg:
        game_category = "TCG"
    elif "VG" in product_str or "VIDEO" in product_str:
        game_category = "VGC"
    elif "GO" in product_str:
        game_category = "GO"
    else:
        game_category = "TCG"

    # Resolve event timezone
    tz_name = store_meta.timezone or "Europe/Paris"
    try:
        tz = pytz.timezone(tz_name)
    except Exception:
        tz = pytz.timezone("Europe/Paris")

    # Date parsing
    start_dt: datetime | None = None
    if date_match:
        raw_dt_str = date_match.group(1).strip()
        try:
            naive_dt = datetime.strptime(raw_dt_str, "%b %d, %Y %H:%M")
            start_dt = tz.localize(naive_dt)
        except Exception:
            pass

    if start_dt is None and dom_date_text:
        parsed_dt = dateparser.parse(
            dom_date_text,
            languages=["fr", "en"],
            settings={"TIMEZONE": tz_name, "RETURN_AS_TIMEZONE_AWARE": True},
        )
        if parsed_dt:
            start_dt = parsed_dt.astimezone(tz)

    if start_dt is None:
        logger.warning("Could not parse date for event '%s' (aria: %s, text: %s)", title, aria_label, dom_date_text)
        return None

    return PokemonEvent(
        guid="",  # Generated deterministically via get_uid()
        store_guid=store_meta.location_guid,
        store_name=store_meta.name,
        title=title,
        game_category=game_category,
        event_type=event_type,
        format="Standard",
        start_time=start_dt,
        timezone=tz_name,
        location_name=store_meta.name,
        location_address=location,
        url=store_meta.original_url,
        raw_data=raw,
    )


def filter_events(events: Sequence[PokemonEvent], filters: StoreFilterConfig) -> list[PokemonEvent]:
    """Keep only events matching a store's filters.

    An empty or missing list in a filter means "no restriction" for that field.
    event_types matches case-insensitively as a substring of the event type (e.g. "Cup" matches "League Cup").
    """
    kept: list[PokemonEvent] = []
    for ev in events:
        if filters.game_categories and ev.game_category not in filters.game_categories:
            continue
        if filters.event_types and not any(f.lower() in ev.event_type.lower() for f in filters.event_types):
            continue
        if filters.exclude_keywords:
            full_text = f"{ev.title} {ev.event_type}".lower()
            if any(kw.lower() in full_text for kw in filters.exclude_keywords):
                continue
        kept.append(ev)
    return kept


class PokemonScraper:
    """Scraper engine for Play! Pokémon Event Locator."""

    def __init__(
        self,
        headless: bool = True,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout_ms: int = 40000,
    ) -> None:
        self.headless = headless
        self.user_agent = user_agent
        self.timeout_ms = timeout_ms

    async def scrape_store(self, store_cfg: StoreConfig) -> list[PokemonEvent]:
        """Scrape all events for a single store."""
        if not store_cfg.enabled:
            logger.info("Store '%s' is disabled. Skipping.", store_cfg.name)
            return []

        store_meta = parse_store_url(store_cfg.url, fallback_name=store_cfg.name)
        logger.info("Scraping store '%s' (GUID: %s, TZ: %s)...", store_meta.name, store_meta.location_guid, store_meta.timezone)

        async with async_playwright() as p:
            browser: Browser = await p.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            context: BrowserContext = await browser.new_context(
                user_agent=self.user_agent,
                locale=store_meta.locale or "fr-FR",
                viewport={"width": 1280, "height": 900},
            )
            page: Page = await context.new_page()

            try:
                await page.goto(store_cfg.url, timeout=self.timeout_ms)
                # Wait for OutSystems SPA container to mount
                await page.wait_for_selector(".el-reskin-layout, #reactContainer", timeout=self.timeout_ms)
                # Allow OutSystems data action to finish populating cards
                await asyncio.sleep(4)

                # Extract event cards from the DOM
                cards_data: list[dict[str, Any]] = await page.evaluate(
                    """() => {
                    const cards = document.querySelectorAll('[data-block="Patterns.MapLocationCard"]');
                    const results = [];
                    cards.forEach(card => {
                        const info = card.querySelector('[aria-label]');
                        const ariaLabel = info ? info.getAttribute('aria-label') : '';
                        const category = card.querySelector('.event-info__category')?.innerText?.trim() || '';
                        const title = card.querySelector('.event-info__title')?.innerText?.trim() || '';
                        const location = card.querySelector('.event-info__info-item__location')?.innerText?.trim() || '';
                        const dateText = card.querySelector('.event-info__info-item__text')?.innerText?.trim() || '';
                        const isTcg = card.querySelector('.map-location-card__gradient--is-tcg') !== null;
                        results.push({ ariaLabel, category, title, location, dateText, isTcg });
                    });
                    return results;
                }"""
                )
            except Exception as exc:
                logger.error("Error scraping store %s: %s", store_cfg.name, exc)
                await browser.close()
                return []

            await browser.close()

        parsed_events = [ev for ev in (parse_event_card_data(raw, store_meta) for raw in cards_data) if ev]
        events = filter_events(parsed_events, store_cfg.filters)

        logger.info("Found %d matching events for '%s'", len(events), store_meta.name)
        return events

    async def scrape_stores(self, stores: Sequence[StoreConfig]) -> list[PokemonEvent]:
        """Scrape events for multiple stores sequentially."""
        all_events: list[PokemonEvent] = []
        for store in stores:
            if not store.enabled:
                continue
            evs = await self.scrape_store(store)
            all_events.extend(evs)
        return all_events

    def scrape_stores_sync(self, stores: Sequence[StoreConfig]) -> list[PokemonEvent]:
        """Synchronous helper for scrape_stores."""
        return asyncio.run(self.scrape_stores(stores))
