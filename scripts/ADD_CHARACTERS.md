# Add Characters

Discovers characters for a given anime from MyAnimeList, fetches their images
from MAL `/pics` pages, and inserts only the new ones into the MongoDB
`characters` collection. Characters are ranked by MAL favourites — most popular
are added first.

## Prerequisites

- MongoDB running on `localhost:27017` (db: `themey`)
- The target anime must exist as an item in MongoDB's `categories` collection
- Python venv activated or `PYTHONPATH` set (see invocation below)

## Invocation

Run from the `theme-rag-builder/` directory:

```bash
# Add up to 10 new characters for One Piece (default)
PYTHONPATH=. venv/bin/python3 scripts/add_characters.py --item "One Piece"

# Add up to N new characters in one run
PYTHONPATH=. venv/bin/python3 scripts/add_characters.py --item "Naruto" --limit 20

# Process every new character (no cap)
PYTHONPATH=. venv/bin/python3 scripts/add_characters.py --item "Attack on Titan" --all

# Preview without writing to MongoDB
PYTHONPATH=. venv/bin/python3 scripts/add_characters.py --item "One Piece" --dry-run

# List all supported anime
PYTHONPATH=. venv/bin/python3 scripts/add_characters.py --list
```

`--limit` defaults to **10**. Use `--all` to process every discovered character.  
`--dry-run` runs the full pipeline but skips the MongoDB insert.

## Pipeline

1. **Discover** — Fetches the anime's cast table from the MAL `/anime/:id/characters`
   page. Only characters listed in that anime's cast are returned (no crossover
   or sidebar links). Results are sorted by MAL favourites descending.

2. **Filter** — Queries MongoDB for existing character names (`categoryKey + itemName`)
   and removes them from the candidate list.

3. **Verify + image** — For each new character, confirms they appear in this anime's
   cast by checking their MAL profile, then scrapes the first image from their
   `/pics` page. Characters that fail verification or have no image are skipped.

4. **Insert** — Writes documents to MongoDB:
   ```json
   { "name": "Monkey D. Luffy", "image": "https://cdn.myanimelist.net/...",
     "categoryKey": "anime", "itemName": "One Piece" }
   ```

## Supporting a New Anime

Add an entry to `agents/anime_presets.py`:

```python
"my anime": AnimePreset(item_name="My Anime", mal_id=12345),
```

`item_name` must match the value in MongoDB exactly. `mal_id` is the numeric ID
from `myanimelist.net/anime/<id>`.

## Rate Limits

MAL scraping uses ~1 s between character requests (profile page + pics page per
character). With `--limit 10` expect roughly 20–30 s of network calls total.

## Environment

`.env` is loaded from the project root (`theme-rag-builder/../.env`).
Override the default with:

```
MONGODB_URI=mongodb://localhost:27017/themey
```

## Orchestrator alternative

The same pipeline is also available as a tool function for the Claude orchestrator:

```python
from tools.anime_db_tools import add_characters
result = add_characters("One Piece", limit=10, dry_run=False)
```

Use the script for direct / admin-panel invocation; use the tool function when
building automated pipelines via `orchestrator/orchestrator_agent.py`.
