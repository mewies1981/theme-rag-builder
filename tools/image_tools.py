"""
Low-level image-fetching helpers shared by:
  - scripts/fetch_topic_images.py  (CLI / admin panel)
  - tools/anime_db_tools.py        (orchestrator tool)
"""

import os
import sys
from pathlib import Path

import requests
from pymongo import MongoClient
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

load_dotenv(_PROJECT_ROOT / ".env")

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/themey")
HEADERS   = {"User-Agent": "Mozilla/5.0 (compatible; theme-universe/1.0)"}


# ── AniList ───────────────────────────────────────────────────────────────────

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


# ── Wikipedia ─────────────────────────────────────────────────────────────────

def fetch_wikipedia_images(topic_name: str) -> list[str]:
    """Return image URLs from the topic's Wikipedia article."""
    IMAGE_EXTS    = (".jpg", ".jpeg", ".png", ".webp")
    SKIP_PREFIXES = ("File:Commons-logo", "File:Wikimedia", "File:Wiki",
                     "File:Question", "File:OOjs", "File:Portal")
    api = "https://en.wikipedia.org/w/api.php"

    try:
        resp = requests.get(
            api,
            params={"action": "query", "list": "search", "srsearch": topic_name,
                    "srlimit": 1, "format": "json"},
            headers=HEADERS, timeout=10,
        )
        results = resp.json().get("query", {}).get("search", [])
        if not results:
            print("  ⚠️  Wikipedia: no article found")
            return []
        page_title = results[0]["title"]
    except Exception as e:
        print(f"  ⚠️  Wikipedia search error: {e}")
        return []

    try:
        resp = requests.get(
            api,
            params={"action": "query", "titles": page_title, "prop": "images",
                    "imlimit": 30, "format": "json"},
            headers=HEADERS, timeout=10,
        )
        pages        = resp.json().get("query", {}).get("pages", {})
        image_titles = [
            img["title"]
            for page in pages.values()
            for img in page.get("images", [])
            if (img["title"].lower().endswith(IMAGE_EXTS)
                and not any(img["title"].startswith(p) for p in SKIP_PREFIXES))
        ]
    except Exception as e:
        print(f"  ⚠️  Wikipedia images list error: {e}")
        return []

    if not image_titles:
        print("  ⚠️  Wikipedia: no usable images on page")
        return []

    try:
        resp = requests.get(
            api,
            params={"action": "query", "titles": "|".join(image_titles[:20]),
                    "prop": "imageinfo", "iiprop": "url", "format": "json"},
            headers=HEADERS, timeout=10,
        )
        pages = resp.json().get("query", {}).get("pages", {})
        urls  = [
            info.get("url", "")
            for page in pages.values()
            for info in page.get("imageinfo", [])
            if info.get("url", "").lower().endswith(IMAGE_EXTS)
        ]
    except Exception as e:
        print(f"  ⚠️  Wikipedia imageinfo error: {e}")
        return []

    print(f"  📖 Wikipedia: {len(urls)} images")
    return urls


# ── MongoDB helpers ───────────────────────────────────────────────────────────

def get_existing_urls(category_key: str, item_name: str) -> set[str]:
    client = MongoClient(MONGO_URI)
    db     = client.get_default_database()
    urls   = {d["url"] for d in db.topic_images.find(
        {"categoryKey": category_key, "itemName": item_name}, {"url": 1}
    )}
    client.close()
    return urls


def delete_existing(category_key: str, item_name: str):
    client = MongoClient(MONGO_URI)
    db     = client.get_default_database()
    n      = db.topic_images.delete_many(
        {"categoryKey": category_key, "itemName": item_name}
    ).deleted_count
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
    db     = client.get_default_database()
    n      = len(db.topic_images.insert_many(docs).inserted_ids)
    client.close()
    return n
