"""
Add Characters script
---------------------
Discovers characters for a given anime from MyAnimeList, fetches their
images from the MAL /pics pages, checks which ones are already in MongoDB,
and inserts only the new ones.

Usage (from theme-rag-builder/):
    PYTHONPATH=. venv/bin/python3 scripts/add_characters.py --item "Naruto"
    PYTHONPATH=. venv/bin/python3 scripts/add_characters.py --item "One Piece" --limit 20
    PYTHONPATH=. venv/bin/python3 scripts/add_characters.py --item "Attack on Titan" --dry-run
    PYTHONPATH=. venv/bin/python3 scripts/add_characters.py --all
    PYTHONPATH=. venv/bin/python3 scripts/add_characters.py --list
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agents.anime_presets import AnimePreset, resolve_preset
from scraper.mal_character_discovery import discover_characters
from scraper.mal_character_images import fetch_images

for env_path in (_PROJECT_ROOT.parent / ".env", _PROJECT_ROOT / ".env"):
    if env_path.exists():
        load_dotenv(env_path)
        break
else:
    load_dotenv()

import os

MONGO_URI    = os.getenv("MONGODB_URI", "mongodb://localhost:27017/themey")
CATEGORY_KEY = "anime"


def get_existing_names(item_name: str) -> set[str]:
    client = MongoClient(MONGO_URI)
    db = client.get_default_database()
    names = {
        d["name"]
        for d in db.characters.find(
            {"categoryKey": CATEGORY_KEY, "itemName": item_name},
            {"name": 1},
        )
    }
    client.close()
    return names


def insert_characters(characters: list[dict], dry_run: bool = False) -> int:
    if not characters:
        return 0
    if dry_run:
        print(f"  [dry-run] Would insert {len(characters)} characters")
        return 0

    client = MongoClient(MONGO_URI)
    db     = client.get_default_database()
    n      = len(db.characters.insert_many(characters).inserted_ids)
    client.close()
    return n


def run(preset: AnimePreset, limit: int | None = 10, dry_run: bool = False):
    print(f"\n🎬 Add Characters — {preset.item_name}")
    print(f"{'[DRY RUN] ' if dry_run else ''}MongoDB: {MONGO_URI}")
    print(f"   MAL anime id: {preset.mal_id}\n")

    print("📡 Discovering cast from MyAnimeList...")
    all_chars = discover_characters(preset.mal_id)
    print(f"\n✅ {len(all_chars)} cast members found for {preset.item_name}\n")

    print("🔍 Checking existing characters in MongoDB...")
    existing = get_existing_names(preset.item_name)
    pending  = [c for c in all_chars if c.name not in existing]
    pending.sort(key=lambda c: c.favorites, reverse=True)
    print(f"   Already in DB : {len(existing)}")
    print(f"   New to add    : {len(pending)} (sorted by MAL favorites, highest first)\n")

    if not pending:
        print("✅ Nothing to add — all discovered characters already exist in MongoDB.")
        return

    if limit is not None and len(pending) > limit:
        top = pending[0]
        print(
            f"🔢 --limit {limit}: processing top {limit} by favorites "
            f"(e.g. {top.name} — {top.favorites:,}).\n"
        )
        pending = pending[:limit]

    print("🖼️  Scraping pictures from MAL /pics pages...\n")
    images = fetch_images(pending, preset.mal_id)

    to_insert: list[dict] = []
    skipped:   list[str]  = []

    for i, char in enumerate(pending):
        result = images.get(char.name)
        print(f"  ({i + 1}/{len(pending)}) {char.name} ({char.favorites:,} fav)", end=" ... ")
        if result:
            print(f"✅ {result.url}")
            to_insert.append({
                "name":        char.name,
                "image":       result.url,
                "categoryKey": CATEGORY_KEY,
                "itemName":    preset.item_name,
            })
        else:
            print("⚠️  no image found — skipped")
            skipped.append(char.name)

    print(f"\n💾 Inserting {len(to_insert)} characters into MongoDB...")
    inserted = insert_characters(to_insert, dry_run=dry_run)

    print(f"\n{'=' * 60}")
    print("✅ Done")
    print(f"   Inserted : {inserted}")
    print(f"   Skipped  : {len(skipped)} (no image found)")
    if skipped:
        print(f"   Skipped names: {', '.join(skipped)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Add characters from MyAnimeList to MongoDB."
    )
    parser.add_argument(
        "--item",
        default="One Piece",
        help="Anime item name or preset key (default: One Piece).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max new characters per run (default: 10). Ignored when --all is set.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process every new character (no limit).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover and fetch images but do not write to MongoDB.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print all supported anime names and exit.",
    )
    args = parser.parse_args()

    if args.list:
        from agents.anime_presets import PRESETS
        print("Supported anime:")
        for name in sorted(p.item_name for p in PRESETS.values()):
            print(f"  • {name}")
        sys.exit(0)

    try:
        preset = resolve_preset(args.item)
    except ValueError as e:
        parser.error(str(e))

    run(
        preset=preset,
        limit=None if args.all else args.limit,
        dry_run=args.dry_run,
    )
