"""
Character Addition Agent
------------------------
Discovers One Piece characters from the fandom wiki, finds their images
via the Jikan API (MAL), checks which ones are already in MongoDB,
and inserts only the new ones.

Usage:
    PYTHONPATH=. venv/bin/python3 agents/character_addition_agent.py
    PYTHONPATH=. venv/bin/python3 agents/character_addition_agent.py --limit 10
    PYTHONPATH=. venv/bin/python3 agents/character_addition_agent.py --dry-run
"""

import argparse
import time
import re
import requests
from pymongo import MongoClient
from dotenv import load_dotenv
import os
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# ── Config ────────────────────────────────────────────────────────────────────

MONGO_URI      = os.getenv("MONGODB_URI", "mongodb://localhost:27017/themey")
JIKAN_BASE     = "https://api.jikan.moe/v4"
ONE_PIECE_MAL  = 21          # MAL anime ID for One Piece
JIKAN_DELAY    = 0.5         # seconds between Jikan requests (rate limit: 3/s)
CATEGORY_KEY   = "anime"
ITEM_NAME      = "One Piece"

# Fandom wiki categories to discover characters from
CHARACTER_CATEGORIES = [
    "Straw Hat Pirates",
    "Four Emperors",
    "Seven Warlords of the Sea",
    "Marines",
    "Whitebeard Pirates",
    "Red Hair Pirates",
    "Worst Generation",
    "Revolutionaries",
    "Cipher Pol",
]

FANDOM_API = "https://onepiece.fandom.com/api.php"
HEADERS    = {"User-Agent": "Mozilla/5.0 (compatible; anime-rag-builder/1.0)"}


# ── Discovery ─────────────────────────────────────────────────────────────────

def discover_character_names() -> list[str]:
    """Fetch all character page titles from fandom wiki categories."""
    seen   = set()
    result = []

    for cat in CHARACTER_CATEGORIES:
        params = {
            "action":      "query",
            "list":        "categorymembers",
            "cmtitle":     f"Category:{cat}",
            "cmlimit":     500,
            "cmnamespace": 0,
            "cmtype":      "page",
            "format":      "json",
        }
        try:
            resp = requests.get(FANDOM_API, params=params, headers=HEADERS, timeout=10)
            members = resp.json().get("query", {}).get("categorymembers", [])
            new = [m["title"] for m in members if m["title"] not in seen]
            for t in new:
                seen.add(t)
                result.append(t)
            print(f"  📂 {cat}: {len(members)} found, {len(new)} new")
        except Exception as e:
            print(f"  ⚠️  Could not fetch category '{cat}': {e}")
        time.sleep(0.3)

    return result


# ── MongoDB ────────────────────────────────────────────────────────────────────

def get_existing_names() -> set[str]:
    """Return the set of character names already in MongoDB for One Piece."""
    client = MongoClient(MONGO_URI)
    db = client.get_default_database()
    docs = db.characters.find(
        {"categoryKey": CATEGORY_KEY, "itemName": ITEM_NAME},
        {"name": 1}
    )
    names = {d["name"] for d in docs}
    client.close()
    return names


def insert_characters(characters: list[dict], dry_run: bool = False) -> int:
    """Insert a list of character dicts into MongoDB. Returns count inserted."""
    if not characters:
        return 0
    if dry_run:
        print(f"  [dry-run] Would insert {len(characters)} characters")
        return 0

    client = MongoClient(MONGO_URI)
    db = client.get_default_database()
    result = db.characters.insert_many(characters)
    client.close()
    return len(result.inserted_ids)


# ── Jikan image lookup ─────────────────────────────────────────────────────────

def _normalize(name: str) -> str:
    """Lowercase, remove punctuation for loose comparison."""
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


def fetch_image(character_name: str) -> str | None:
    """
    Search Jikan for the character, scoped to One Piece (MAL ID 21).
    Returns the MAL image URL or None if not found.
    """
    url = f"{JIKAN_BASE}/characters"
    params = {"q": character_name, "limit": 5}

    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except Exception as e:
        print(f"    ⚠️  Jikan error for '{character_name}': {e}")
        return None

    if not data:
        return None

    norm_query = _normalize(character_name)

    # Prefer exact name match
    for item in data:
        if _normalize(item.get("name", "")) == norm_query:
            return item.get("images", {}).get("jpg", {}).get("image_url")

    # Fall back to first result if name is a substring match
    first = data[0]
    first_name = _normalize(first.get("name", ""))
    if norm_query in first_name or first_name in norm_query:
        return first.get("images", {}).get("jpg", {}).get("image_url")

    return None


# ── Main ──────────────────────────────────────────────────────────────────────

def run(limit: int = None, dry_run: bool = False):
    print(f"\n🤖 Character Addition Agent — {ITEM_NAME}")
    print(f"{'[DRY RUN] ' if dry_run else ''}MongoDB: {MONGO_URI}\n")

    # Step 1: discover candidates from fandom wiki
    print("📡 Discovering characters from fandom wiki categories...")
    all_names = discover_character_names()
    print(f"\n✅ {len(all_names)} characters discovered across {len(CHARACTER_CATEGORIES)} categories\n")

    # Step 2: filter out already-existing ones
    print("🔍 Checking existing characters in MongoDB...")
    existing = get_existing_names()
    pending = [n for n in all_names if n not in existing]
    print(f"   Already in DB : {len(existing)}")
    print(f"   New to add    : {len(pending)}\n")

    if not pending:
        print("✅ Nothing to add — all discovered characters already exist in MongoDB.")
        return

    # Apply limit
    if limit and len(pending) > limit:
        print(f"🔢 --limit {limit}: processing first {limit} of {len(pending)} new characters.\n")
        pending = pending[:limit]

    # Step 3: fetch images and build documents
    print("🌐 Fetching images from Jikan (MAL)...\n")
    to_insert = []
    skipped   = []

    for i, name in enumerate(pending):
        print(f"  ({i+1}/{len(pending)}) {name}", end=" ... ")
        image = fetch_image(name)
        time.sleep(JIKAN_DELAY)

        if image:
            print(f"✅ {image}")
            to_insert.append({
                "name":        name,
                "image":       image,
                "categoryKey": CATEGORY_KEY,
                "itemName":    ITEM_NAME,
            })
        else:
            print("⚠️  no image found — skipped")
            skipped.append(name)

    # Step 4: insert into MongoDB
    print(f"\n💾 Inserting {len(to_insert)} characters into MongoDB...")
    inserted = insert_characters(to_insert, dry_run=dry_run)

    print(f"\n{'='*60}")
    print(f"✅ Done")
    print(f"   Inserted : {inserted}")
    print(f"   Skipped  : {len(skipped)} (no image found)")
    if skipped:
        print(f"   Skipped names: {', '.join(skipped)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit",   type=int, default=10, help="Max new characters to add per run (default: 10)")
    parser.add_argument("--dry-run", action="store_true",  help="Discover and fetch images but do not write to MongoDB")
    args = parser.parse_args()
    run(limit=args.limit, dry_run=args.dry_run)
