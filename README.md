# PokéCal ⚡

> **Play! Pokémon TCG Event Sync for Google Calendar, Apple Calendar, and Outlook via Open iCalendar (RFC 5545 / Webcal)**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Open Standard](https://img.shields.io/badge/RFC-5545%20iCalendar-success.svg)](https://datatracker.ietf.org/doc/html/rfc5545)

PokéCal synchronizes Pokémon Trading Card Game (TCG) tournaments—including **Weekly Leagues**, **League Challenges**, **League Cups**, and **Prereleases**—from the official **Play! Pokémon Event Locator** (`events.pokemon.com`) directly to your calendar.

Because it outputs standard RFC 5545 `.ics` (iCalendar / Webcal) feeds, **zero Google Cloud API keys, OAuth screens, or developer credentials are required**. End-users can simply subscribe via *"Add from URL"*.

---

## Features

- **Open Calendar Standard (RFC 5545):** Seamlessly import into Google Calendar, Apple Calendar, Microsoft Outlook, or Thunderbird.
- **Offline Timezone Mapping:** Automatically derives exact IANA timezones (e.g., `Europe/Paris`) from store venue GPS coordinates with no external API quotas.
- **Deterministic Deduplication:** Generates stable, deterministic UIDs (`pokemon-tcg-{store_guid}-{date}-{hash}@pokecal`) to avoid duplicate entries across syncs.
- **Rich Event Formatting:** Categorized emoji tags (🏆 for Cups, 🥇 for Challenges, 🎁 for Prereleases, 🎴 for Leagues), complete venue addresses, official direct URLs, and custom refresh intervals (`X-PUBLISHED-TTL: PT6H`).
- **Headless OutSystems Scraping:** Uses Python Playwright to cleanly render the single-page application (SPA) and extract real-time tournament schedules.
- **Store Search & Favorites:** `pokecal search <city>` finds stores near a town and saves your favorites to `stores.yaml`.
- **Automated GitHub Pages Publishing:** Ready-to-use GitHub Action (`.github/workflows/sync.yml`) runs daily and hosts your calendar feed for free.
- **Scheduled Copilot Issue Implementation:** An optional workflow processes one well-scoped `agent-ready` issue daily and opens a pull request.

---

## Quick Start

### 1. Installation

PokéCal uses [`uv`](https://github.com/astral-sh/uv) for fast, reproducible dependency management:

```bash
# Clone the repository
git clone https://github.com/your-username/pokecal.git
cd pokecal

# Install dependencies and Playwright Chromium
uv sync
uv run playwright install chromium
```

### PostgreSQL for a future bot

The Discord bot is not part of PokéCal yet, and the current CLI does not connect to this database. To start PostgreSQL for future bot development or hosting:

```bash
cp .env.example .env
# Set POSTGRES_PASSWORD in .env to a strong, unique password before hosting.
docker compose up -d
```

The database is available on `localhost:${POSTGRES_PORT:-5432}` from the host. A bot added to this Compose project can connect to `db:5432` on the Compose network. Data persists in the `postgres_data` volume; `docker compose down` preserves it, while `docker compose down -v` deletes it. The host port is bound to localhost and is not exposed publicly.

### 2. Configuration (`stores.yaml`)

Define your target local game store(s) in `stores.yaml`:

```yaml
output:
  ics_path: "dist/pokecal.ics"
  calendar_name: "Pokémon TCG Events"
  calendar_description: "Pokémon TCG Tournaments synchronized by PokéCal"
  default_timezone: "Europe/Paris"

stores:
  - name: "Le coin des barons - Paris Rivoli"
    url: "https://events.pokemon.com/EventLocator/LocationDetail?EventDetailGUID=&range=25&latitude=48.8575475&startdate=2026-11-07&LocationGuid=d31263f1-80fb-0a60-8b04-72c8887c24f2&storename=LE+COIN+DES+BARONS+-+PARIS+RIVOLI&iskm=false&locale=en-US&LocationName=LE+COIN+DES+BARONS+-+PARIS+RIVOLI&longitude=2.3513765"
    enabled: true
    filters:
      game_categories:
        - "TCG"
      # event_types: ["Cup"]          # optional: keep only matching event types
      # exclude_keywords: ["Junior"]  # optional: drop events whose title or type contains these
```

Each store has its own `filters`, so one store can sync every event while another only syncs cups:

```yaml
  - name: "Cups only"
    url: "https://events.pokemon.com/EventLocator/LocationDetail?LocationGuid=..."
    enabled: true
    filters:
      event_types:
        - "Cup"
```

Filter behaviour:
- `game_categories`: keep events whose game matches (default `["TCG"]`).
- `event_types`: optional. When omitted or empty, all event types are kept. Otherwise an event is kept if its type contains one of the listed words, case-insensitively (`"Cup"` matches `League Cup`).
- `exclude_keywords`: optional. Drop events whose title or type contains any listed word, case-insensitively.

### 3. Generate Calendar Feed

```bash
uv run pokecal sync
```

This exports `dist/pokecal.ics` with all upcoming tournaments discovered for your configured venues.

---

## CLI Commands

PokéCal includes a rich command-line interface:

### `pokecal sync`
Scrapes all enabled stores and outputs the calendar feed:
```bash
uv run pokecal sync
# Or with a custom configuration/output:
uv run pokecal sync --config my_stores.yaml --output my_calendar.ics
```

### `pokecal inspect-store <url>`
Parses a Play! Pokémon Event Locator URL to extract the store name, GUID, coordinates, and local timezone:
```bash
uv run pokecal inspect-store "<STORE_URL>"
# Also test fetching live events directly:
uv run pokecal inspect-store "<STORE_URL>" --fetch
```

### `pokecal search <city>`
Searches the locator for stores around a city and saves favorites to `stores.yaml`:
```bash
uv run pokecal search Lyon
# Options: --range 50, --km, --config my_stores.yaml
```
A visible browser window opens (the locator blocks headless browsers). Pick a town from the autocomplete suggestions, then enter the numbers of the stores to save. Each favorite is appended to `stores.yaml` as a `LocationDetail` URL carrying the store's own GUID and coordinates; existing content is left untouched and duplicates are skipped. The search itself is not persisted.

### `pokecal init`
Creates a starter `stores.yaml` configuration template:
```bash
uv run pokecal init
```

---

## Subscribing to Your Feed

### Google Calendar
1. On your computer, open [Google Calendar](https://calendar.google.com).
2. On the left, next to **Other calendars**, click **+** &rarr; **From URL**.
3. Enter the URL of your hosted `.ics` file (e.g. your GitHub Pages URL: `https://your-username.github.io/pokecal/pokecal.ics`).
4. Click **Add calendar**. Google Calendar will periodically fetch updates automatically!

### Apple Calendar (iOS / macOS)
1. Open Calendar on Mac or iOS.
2. Select **File** &rarr; **New Calendar Subscription...**
3. Paste the `.ics` or `webcal://` URL and click **Subscribe**.

### Outlook
1. Go to Outlook Calendar &rarr; **Add Calendar** &rarr; **Subscribe from web**.
2. Paste your `.ics` URL and save.

---

## Automated GitHub Pages Deployment

A ready-to-run GitHub Action is provided in [`.github/workflows/sync.yml`](.github/workflows/sync.yml).

Every day at 04:00 UTC (or manually via `workflow_dispatch`), the workflow:
1. Spawns an automated runner.
2. Scrapes the latest event schedule for all configured stores.
3. Generates the updated `.ics` file.
4. Deploys the feed to GitHub Pages at `https://<username>.github.io/<repo>/pokecal.ics`.

To activate GitHub Pages in your repository:
- Go to **Settings** &rarr; **Pages**.
- Under **Build and deployment**, select **Source: GitHub Actions**.

## Scheduled Copilot Issue Implementation

The optional [Copilot issue workflow](.github/workflows/copilot-issues.yml) runs at 04:00 UTC and processes one open issue labeled `agent-ready`. It is also available from the Actions tab with an optional issue number. The workflow claims the issue with `agent-working`, asks Copilot to implement it and run relevant tests, then opens a pull request using the repository template.

To enable it, add a `COPILOT_TOKEN` repository secret: a fine-grained personal access token with only the **Copilot Requests** permission, belonging to an account licensed for GitHub Copilot. The agent runs with that token alone; branch push, pull request and label changes are done by a separate step using the workflow's `GITHUB_TOKEN`, so also enable **Settings** &rarr; **Actions** &rarr; **General** &rarr; **Allow GitHub Actions to create and approve pull requests**. Only issues authored by repository members, and comments from members, are given to the agent, and changes under `.github/` are rejected.

Issues created with the **Agent task (user story)** template are ready for this workflow when their scope and acceptance criteria are complete. If Copilot needs clarification or a product decision, it creates no pull request, adds a comment with the questions, replaces `agent-working` with `needs-refinement`, and stops. Add `agent-ready` again after resolving the questions to return the issue to the queue.

---

## Testing

Run the unit test suite with pytest:

```bash
uv run pytest
```

Tests are **unit tests only**: they run offline and use recorded fixtures or mocks instead of the live site. End-to-end tests are intentionally out of scope for this project.

## Development

Contributors and AI development agents must read [`AGENT.md`](AGENT.md) before changing code. It covers the required inspection of the live site before scraping work, the planned store search feature, and the testing rules.

## Roadmap

- **Store search (implemented):** `pokecal search <city>`; see CLI Commands. Favourite stores may be in different towns from the search point.
- **Discord bot (planned, later):** a Discord interface built on the official Discord API. Out of scope for now.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
