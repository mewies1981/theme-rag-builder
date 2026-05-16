# Character Addition Agent

Discovers characters for an anime from its fandom wiki, looks up their images via the Jikan API (MyAnimeList), and inserts only the new ones into the MongoDB `characters` collection.

## Prerequisites

- MongoDB running on `localhost:27017` (db: `themey`)
- The target anime must already exist as an item inside a `categories` document in MongoDB
- Python venv activated or `PYTHONPATH` set (see invocation below)

## Invocation

Run from the `theme-rag-builder/` directory:

```bash
# Add up to 10 new characters for One Piece (default)
PYTHONPATH=. venv/bin/python3 agents/character_addition_agent.py

# Add up to N new characters in one run
PYTHONPATH=. venv/bin/python3 agents/character_addition_agent.py --limit 20

# Target a different anime preset (see agents/anime_presets.py)
PYTHONPATH=. venv/bin/python3 agents/character_addition_agent.py --item Naruto --limit 15

# Process every new character (no cap)
PYTHONPATH=. venv/bin/python3 agents/character_addition_agent.py --all

# Preview what would be added without writing to MongoDB
PYTHONPATH=. venv/bin/python3 agents/character_addition_agent.py --dry-run
```

`--limit` defaults to **10**. Use `--all` to process every discovered character without a cap.  
`--dry-run` runs the full discovery + Jikan lookup but skips the MongoDB insert.

## What the Agent Does

The agent runs a four-step pipeline:

1. **Discover** — Queries the target anime's fandom wiki API (`categorymembers`) for each configured wiki category (e.g. "Straw Hat Pirates", "Marines"). Deduplicates across categories.

2. **Filter** — Fetches existing character names from MongoDB (`categoryKey` + `itemName` match) and removes them from the candidate list.

3. **Image lookup** — For each new name, calls the Jikan REST API (`/v4/characters?q=<name>&limit=5`). Prefers an exact name match; falls back to a substring match on the first result. Sleeps 0.5 s between requests to stay within Jikan's rate limit.

4. **Insert** — Writes only characters that received a valid image URL. Each document written to MongoDB has the shape:
```json
{
  "name":        "Monkey D. Luffy",
  "image":       "https://cdn.myanimelist.net/...",
  "categoryKey": "anime",
  "itemName":    "One Piece"
}
```

Characters with no Jikan image match are skipped and reported in the summary.

## Adapting for a Different Anime

Use `--item` with a built-in preset (`One Piece`, `Naruto`, or keys `one piece` / `naruto`), or add a new entry to `agents/anime_presets.py`:

| Field | What to set |
|-------|-------------|
| `item_name` | The item name as it appears in MongoDB, e.g. `"Naruto"` |
| `wiki` | Fandom subdomain, e.g. `"naruto"` → `naruto.fandom.com` |
| `mal_id` | MAL anime ID (reserved for future scoped Jikan search) |
| `categories` | Wiki category names to scrape — check the fandom wiki's category tree |

`mal_id` is not yet used in character search (Jikan search is by name only).

## Rate Limits

- **Fandom wiki**: 0.3 s sleep between category requests — no known hard limit.
- **Jikan**: 0.5 s sleep between character lookups. Jikan's public limit is 3 requests/second; the 0.5 s delay keeps the agent well within it. If you hit 429s, increase `JIKAN_DELAY`.

## Environment

The agent loads `.env` from the **project root** (`theme-rag-builder/../.env`), not from its own directory. Set `MONGODB_URI` there to override the default:

```
MONGODB_URI=mongodb://localhost:27017/themey
```
