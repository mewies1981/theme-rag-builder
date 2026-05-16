"""
Fetch Topic Images script
-------------------------
Fetches artwork images for a given topic and stores them in the
MongoDB `topic_images` collection.

Sources (in order):
  1. AniList GraphQL  — anime topics only (cover + banner + character art)
  2. Wikipedia media  — any topic (images embedded in the Wikipedia article)

Usage (from theme-rag-builder/):
    PYTHONPATH=. venv/bin/python3 scripts/fetch_topic_images.py --item "One Piece" --category anime
    PYTHONPATH=. venv/bin/python3 scripts/fetch_topic_images.py --item "Inception" --category movies
    PYTHONPATH=. venv/bin/python3 scripts/fetch_topic_images.py --item "One Piece" --category anime --dry-run
    PYTHONPATH=. venv/bin/python3 scripts/fetch_topic_images.py --item "One Piece" --category anime --reset
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

load_dotenv(_PROJECT_ROOT / ".env")

from tools.image_tools import (
    fetch_anilist_images,
    fetch_wikipedia_images,
    get_existing_urls,
    delete_existing,
    insert_images,
)

import os
MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/themey")


def run(item_name: str, category_key: str, dry_run: bool = False, reset: bool = False):
    print(f"\n🖼️  Fetch Topic Images — {item_name} ({category_key})")
    print(f"{'[DRY RUN] ' if dry_run else ''}MongoDB: {MONGO_URI}\n")

    if reset and not dry_run:
        delete_existing(category_key, item_name)

    all_urls: list[tuple[str, str]] = []  # (url, source)

    if category_key == "anime":
        print("📡 Fetching from AniList...")
        for url in fetch_anilist_images(item_name):
            all_urls.append((url, "anilist"))

    print("📡 Fetching from Wikipedia...")
    for url in fetch_wikipedia_images(item_name):
        all_urls.append((url, "wikipedia"))

    print(f"\n   Total fetched : {len(all_urls)}")

    if not reset:
        existing  = get_existing_urls(category_key, item_name)
        all_urls  = [(u, s) for u, s in all_urls if u not in existing]
        print(f"   New to insert  : {len(all_urls)}")

    if not all_urls:
        print("\n✅ Nothing new to add.")
        return

    docs = [
        {"categoryKey": category_key, "itemName": item_name, "url": u, "source": s}
        for u, s in all_urls
    ]
    inserted = insert_images(docs, dry_run)
    print(f"\n{'=' * 50}")
    print(f"✅ Done — inserted {inserted} images for '{item_name}'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch topic images from AniList and Wikipedia into MongoDB."
    )
    parser.add_argument("--item",     required=True, help="Topic name, e.g. 'One Piece'")
    parser.add_argument("--category", required=True, help="Category key, e.g. 'anime'")
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--reset",    action="store_true",
                        help="Delete existing images for this topic first.")
    args = parser.parse_args()
    run(args.item, args.category, dry_run=args.dry_run, reset=args.reset)
