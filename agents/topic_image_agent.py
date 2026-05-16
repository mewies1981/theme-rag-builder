"""
Topic Image Agent
-----------------
Fetches artwork images for a given topic and stores them in the
MongoDB `topic_images` collection.

Sources (in order):
  1. AniList GraphQL  — anime topics only (cover + banner + character art)
  2. Wikipedia media  — any topic (images embedded in the Wikipedia article)

Usage:
    PYTHONPATH=. venv/bin/python3 agents/topic_image_agent.py --item "One Piece" --category anime
    PYTHONPATH=. venv/bin/python3 agents/topic_image_agent.py --item "Inception" --category movies
    PYTHONPATH=. venv/bin/python3 agents/topic_image_agent.py --item "One Piece" --category anime --dry-run
    PYTHONPATH=. venv/bin/python3 agents/topic_image_agent.py --item "One Piece" --category anime --reset
"""

import argparse
import requests
from pymongo import MongoClient
from dotenv import load_dotenv
import os
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/themey")
HEADERS   = {"User-Agent": "Mozilla/5.0 (compatible; theme-universe/1.0)"}


# ── AniList (anime only) ───────────────────────────────────────────────────────

def fetch_anilist_images(anime_name: str) -> list[str]:
    """Return cover, banner, and top character images from AniList."""
    query = """
    query ($search: String) {
      Media(search: $search, type: ANIME) {
        coverImage { extraLarge large }
        bannerImage
        characters(sort: ROLE, page: 1, perPage: 10) {
          nodes { image { large } }
        }
      }
    }
    """
    try:
        resp = requests.post(
            "https://graphql.anilist.co",
            json={"query": query, "variables": {"search": anime_name}},
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        media = resp.json().get("data", {}).get("Media")
        if not media:
            print("  ⚠️  AniList: no result found")
            return []
    except Exception as e:
        print(f"  ⚠️  AniList error: {e}")
        return []

    urls = []

    cover = media.get("coverImage", {})
    for key in ("extraLarge", "large"):
        if cover.get(key):
            urls.append(cover[key])
            break

    if media.get("bannerImage"):
        urls.append(media["bannerImage"])

    for node in media.get("characters", {}).get("nodes", []):
        img = node.get("image", {}).get("large")
        if img:
            urls.append(img)

    print(f"  📺 AniList: {len(urls)} images")
    return urls


# ── Wikipedia (all categories) ────────────────────────────────────────────────

def fetch_wikipedia_images(topic_name: str) -> list[str]:
    """Return image URLs from the topic's Wikipedia article."""
    IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
    SKIP_PREFIXES = ("File:Commons-logo", "File:Wikimedia", "File:Wiki",
                     "File:Question", "File:OOjs", "File:Portal")

    # Resolve the Wikipedia page title
    search_url = "https://en.wikipedia.org/w/api.php"
    try:
        resp = requests.get(
            search_url,
            params={"action": "query", "list": "search", "srsearch": topic_name,
                    "srlimit": 1, "format": "json"},
            headers=HEADERS,
            timeout=10,
        )
        results = resp.json().get("query", {}).get("search", [])
        if not results:
            print("  ⚠️  Wikipedia: no article found")
            return []
        page_title = results[0]["title"]
    except Exception as e:
        print(f"  ⚠️  Wikipedia search error: {e}")
        return []

    # Get list of images used on the page
    try:
        resp = requests.get(
            search_url,
            params={"action": "query", "titles": page_title, "prop": "images",
                    "imlimit": 30, "format": "json"},
            headers=HEADERS,
            timeout=10,
        )
        pages = resp.json().get("query", {}).get("pages", {})
        image_titles = []
        for page in pages.values():
            for img in page.get("images", []):
                title = img["title"]
                if (title.lower().endswith(IMAGE_EXTS)
                        and not any(title.startswith(p) for p in SKIP_PREFIXES)):
                    image_titles.append(title)
    except Exception as e:
        print(f"  ⚠️  Wikipedia images list error: {e}")
        return []

    if not image_titles:
        print("  ⚠️  Wikipedia: no usable images on page")
        return []

    # Resolve each file title to a direct URL (batch, max 50)
    urls = []
    try:
        resp = requests.get(
            search_url,
            params={"action": "query", "titles": "|".join(image_titles[:20]),
                    "prop": "imageinfo", "iiprop": "url", "format": "json"},
            headers=HEADERS,
            timeout=10,
        )
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            for info in page.get("imageinfo", []):
                url = info.get("url", "")
                if url.lower().endswith(IMAGE_EXTS):
                    urls.append(url)
    except Exception as e:
        print(f"  ⚠️  Wikipedia imageinfo error: {e}")

    print(f"  📖 Wikipedia: {len(urls)} images")
    return urls


# ── MongoDB ────────────────────────────────────────────────────────────────────

def get_existing_urls(category_key: str, item_name: str) -> set[str]:
    client = MongoClient(MONGO_URI)
    db = client.get_default_database()
    existing = {d["url"] for d in db.topic_images.find(
        {"categoryKey": category_key, "itemName": item_name}, {"url": 1}
    )}
    client.close()
    return existing


def delete_existing(category_key: str, item_name: str):
    client = MongoClient(MONGO_URI)
    db = client.get_default_database()
    n = db.topic_images.delete_many({"categoryKey": category_key, "itemName": item_name}).deleted_count
    client.close()
    print(f"  🗑️  Removed {n} existing images")


def insert_images(docs: list[dict], dry_run: bool) -> int:
    if not docs:
        return 0
    if dry_run:
        print(f"  [dry-run] Would insert {len(docs)} images")
        for d in docs:
            print(f"    {d['source']:10} {d['url'][:80]}")
        return 0
    client = MongoClient(MONGO_URI)
    db = client.get_default_database()
    n = len(db.topic_images.insert_many(docs).inserted_ids)
    client.close()
    return n


# ── Main ───────────────────────────────────────────────────────────────────────

def run(item_name: str, category_key: str, dry_run: bool = False, reset: bool = False):
    print(f"\n🖼️  Topic Image Agent — {item_name} ({category_key})")
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

    # Deduplicate against DB (unless resetting)
    if not reset:
        existing = get_existing_urls(category_key, item_name)
        all_urls = [(u, s) for u, s in all_urls if u not in existing]
        print(f"   New to insert  : {len(all_urls)}")

    if not all_urls:
        print("\n✅ Nothing new to add.")
        return

    docs = [
        {"categoryKey": category_key, "itemName": item_name, "url": u, "source": s}
        for u, s in all_urls
    ]

    inserted = insert_images(docs, dry_run)
    print(f"\n{'='*50}")
    print(f"✅ Done — inserted {inserted} images for '{item_name}'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--item",     required=True, help="Topic name, e.g. 'One Piece'")
    parser.add_argument("--category", required=True, help="Category key, e.g. 'anime'")
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--reset",    action="store_true", help="Delete existing images first")
    args = parser.parse_args()
    run(args.item, args.category, dry_run=args.dry_run, reset=args.reset)
