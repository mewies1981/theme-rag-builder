"""
Deterministic tool functions that the orchestrator agent can call.

Each function returns a JSON-serialisable dict with a "success" key.
No LLM calls happen here — these are pure data operations.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

load_dotenv(_PROJECT_ROOT / ".env")

MONGO_URI    = os.getenv("MONGODB_URI", "mongodb://localhost:27017/themey")
CATEGORY_KEY = "anime"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mongo_db():
    client = MongoClient(MONGO_URI)
    return client, client.get_default_database()


# ── Add a new anime ───────────────────────────────────────────────────────────

def _lookup_anime_info(name: str) -> dict:
    """
    Try AniList then Jikan to resolve a cover image and MAL ID for an anime.
    Returns { image, mal_id } — either field may be None if not found.
    """
    import requests
    HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; theme-rag-builder/1.0)"}
    image   = None
    mal_id  = None

    # AniList — best quality cover images
    try:
        query = """
        query ($search: String) {
          Media(search: $search, type: ANIME) {
            coverImage { extraLarge large }
          }
        }
        """
        resp = requests.post(
            "https://graphql.anilist.co",
            json={"query": query, "variables": {"search": name}},
            headers={**HEADERS, "Content-Type": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        media = resp.json().get("data", {}).get("Media")
        if media:
            cover = media.get("coverImage", {})
            image = cover.get("extraLarge") or cover.get("large")
    except Exception:
        pass

    # Jikan — MAL ID + fallback image
    try:
        resp = requests.get(
            "https://api.jikan.moe/v4/anime",
            params={"q": name, "limit": 3},
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if data:
            mal_id = data[0]["mal_id"]
            if not image:
                image = data[0].get("images", {}).get("jpg", {}).get("image_url")
    except Exception:
        pass

    return {"image": image, "mal_id": mal_id}


def add_anime(name: str, image: str | None = None, mal_id: int | None = None) -> dict:
    """
    Add a new anime to the MongoDB categories collection and return the
    resolved image URL and MAL ID so the orchestrator can immediately call
    add_characters or fetch_topic_images without a separate lookup.

    If image is omitted, it is fetched from AniList then Jikan.
    If mal_id is omitted, it is fetched from Jikan.
    """
    client, db = _mongo_db()

    # Duplicate check (case-insensitive)
    doc = db.categories.find_one({"categoryKey": CATEGORY_KEY}, {"items.name": 1})
    if doc:
        existing_names = [item["name"] for item in doc.get("items", [])]
        if any(n.lower() == name.lower() for n in existing_names):
            client.close()
            return {
                "success": False,
                "error":   f"'{name}' already exists in the database.",
                "existing_names": existing_names,
            }

    # Resolve image and/or MAL ID if not provided
    if not image or not mal_id:
        info = _lookup_anime_info(name)
        image  = image  or info["image"]
        mal_id = mal_id or info["mal_id"]

    if not image:
        client.close()
        return {
            "success": False,
            "error":   (
                f"Could not find a cover image for '{name}'. "
                "Pass image=<URL> explicitly."
            ),
        }

    # Insert into categories
    db.categories.update_one(
        {"categoryKey": CATEGORY_KEY},
        {"$push": {"items": {"name": name, "image": image}}},
    )
    client.close()

    result = {
        "success": True,
        "anime":   name,
        "image":   image,
        "message": f"'{name}' added to the anime category.",
    }
    if mal_id:
        result["mal_id"] = mal_id
        result["note"]   = "Use mal_id with add_characters to populate characters."
    return result


# ── Live anime list ───────────────────────────────────────────────────────────

def list_anime() -> dict:
    """
    Return all anime titles currently in the MongoDB categories collection.
    Use this to discover which anime are available before operating on them.
    """
    client, db = _mongo_db()
    doc = db.categories.find_one({"categoryKey": CATEGORY_KEY}, {"items": 1})
    client.close()
    if not doc:
        return {"success": False, "error": "Anime category not found in MongoDB."}
    items = [item["name"] for item in doc.get("items", [])]
    return {"success": True, "count": len(items), "anime": items}


# ── Status check (combine all three signals in one call) ──────────────────────

def check_anime_status(anime: str) -> dict:
    """
    Return a snapshot of what currently exists in the database for the given
    anime: character count + sample names, topic-image count, and a count of
    RAG documents in ChromaDB.
    """
    item_name = anime

    # MongoDB — characters
    client, db = _mongo_db()
    char_count = db.characters.count_documents(
        {"categoryKey": CATEGORY_KEY, "itemName": item_name}
    )
    sample_chars = [
        d["name"]
        for d in db.characters.find(
            {"categoryKey": CATEGORY_KEY, "itemName": item_name}, {"name": 1, "_id": 0}
        ).sort("_id", -1).limit(5)
    ]

    # MongoDB — topic images
    img_count = db.topic_images.count_documents(
        {"categoryKey": CATEGORY_KEY, "itemName": item_name}
    )
    client.close()

    # ChromaDB — RAG documents
    rag_count = 0
    try:
        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        from config import DB_PATH, COLLECTION_NAME, EMBED_MODEL

        ef  = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
        col = chromadb.PersistentClient(path=DB_PATH).get_or_create_collection(
            COLLECTION_NAME, embedding_function=ef
        )
        results  = col.get(where={"anime": item_name}, include=[])
        rag_count = len(results["ids"])
    except Exception:
        rag_count = -1  # ChromaDB unavailable

    return {
        "success":       True,
        "anime":         item_name,
        "characters":    {"count": char_count, "recent": sample_chars},
        "topic_images":  {"count": img_count},
        "rag_documents": {"count": rag_count, "note": "−1 means ChromaDB unavailable"},
    }


# ── Characters ────────────────────────────────────────────────────────────────

def _resolve_mal_id(anime: str) -> int | None:
    """
    Return the MAL anime ID for a title.
    Checks the local presets first; falls back to a Jikan anime search.
    """
    import requests

    # Local presets (instant)
    try:
        from agents.anime_presets import resolve_preset
        return resolve_preset(anime).mal_id
    except ValueError:
        pass

    # Jikan anime search (network)
    try:
        resp = requests.get(
            "https://api.jikan.moe/v4/anime",
            params={"q": anime, "limit": 3},
            headers={"User-Agent": "Mozilla/5.0 (compatible; theme-rag-builder/1.0)"},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("data", [])
        if results:
            return results[0]["mal_id"]
    except Exception as e:
        print(f"  ⚠️  MAL ID lookup failed for '{anime}': {e}")

    return None


def add_characters(
    anime: str,
    limit: int = 10,
    dry_run: bool = False,
    mal_id: int | None = None,
) -> dict:
    """
    Discover characters from MyAnimeList for the given anime, fetch their
    images, and insert only the ones not already in MongoDB.

    Characters are ranked by MAL favourites — most popular are added first.
    mal_id is optional: if omitted the function resolves it from local presets
    or a live Jikan search.
    """
    from scraper.mal_character_discovery import discover_characters
    from scraper.mal_character_images import fetch_images

    item_name = anime

    if mal_id is None:
        mal_id = _resolve_mal_id(anime)
        if mal_id is None:
            return {
                "success": False,
                "error":   (
                    f"Could not find a MAL ID for '{anime}'. "
                    "Pass mal_id explicitly if you know it."
                ),
            }

    # Existing names
    client, db = _mongo_db()
    existing = {
        d["name"]
        for d in db.characters.find(
            {"categoryKey": CATEGORY_KEY, "itemName": item_name}, {"name": 1}
        )
    }
    before_count = len(existing)

    # Discover from MAL
    print(f"  Discovering cast for {item_name} (MAL id={mal_id})…")
    all_chars = discover_characters(mal_id)

    pending = [c for c in all_chars if c.name not in existing]
    pending.sort(key=lambda c: c.favorites, reverse=True)

    if not pending:
        client.close()
        return {
            "success":        True,
            "anime":          item_name,
            "already_in_db":  before_count,
            "inserted":       0,
            "message":        "All discovered characters already in MongoDB.",
        }

    pending = pending[:limit]

    # Fetch images (also verifies cast membership)
    print(f"  Fetching images for {len(pending)} new character(s)…")
    images = fetch_images(pending, mal_id)

    to_insert = []
    skipped   = []
    for char in pending:
        result = images.get(char.name)
        if result:
            to_insert.append({
                "name":        char.name,
                "image":       result.url,
                "categoryKey": CATEGORY_KEY,
                "itemName":    item_name,
            })
        else:
            skipped.append(char.name)

    inserted = 0
    if to_insert and not dry_run:
        inserted = len(db.characters.insert_many(to_insert).inserted_ids)
    client.close()

    return {
        "success":         True,
        "anime":           item_name,
        "discovered_total": len(all_chars),
        "already_in_db":   before_count,
        "processed":       len(pending),
        "inserted":        inserted if not dry_run else f"{len(to_insert)} (dry_run)",
        "skipped":         len(skipped),
        "skipped_names":   skipped[:10],
        "dry_run":         dry_run,
    }


# ── Topic images ──────────────────────────────────────────────────────────────

def fetch_topic_images(
    anime: str,
    category: str = "anime",
    reset: bool   = False,
    dry_run: bool = False,
) -> dict:
    """
    Fetch artwork images for an anime from AniList (anime only) and Wikipedia,
    then store new ones in the MongoDB topic_images collection.

    Set reset=True to wipe existing images first (useful when images are stale).
    """
    from tools.image_tools import (
        fetch_anilist_images,
        fetch_wikipedia_images,
        get_existing_urls,
        delete_existing,
        insert_images,
    )

    all_urls: list[tuple[str, str]] = []  # (url, source)

    if category == "anime":
        for url in fetch_anilist_images(anime):
            all_urls.append((url, "anilist"))

    for url in fetch_wikipedia_images(anime):
        all_urls.append((url, "wikipedia"))

    fetched = len(all_urls)

    if reset and not dry_run:
        delete_existing(category, anime)
        existing: set[str] = set()
    else:
        existing = get_existing_urls(category, anime)

    new_urls = [(u, s) for u, s in all_urls if u not in existing]

    if not new_urls:
        return {
            "success":  True,
            "anime":    anime,
            "fetched":  fetched,
            "inserted": 0,
            "message":  "No new images to add.",
        }

    docs = [
        {"categoryKey": category, "itemName": anime, "url": u, "source": s}
        for u, s in new_urls
    ]
    inserted = insert_images(docs, dry_run=dry_run)

    return {
        "success":     True,
        "anime":       anime,
        "fetched":     fetched,
        "already_had": len(existing),
        "new_found":   len(new_urls),
        "inserted":    inserted if not dry_run else f"{len(new_urls)} (dry_run)",
        "reset":       reset,
        "dry_run":     dry_run,
    }


# ── RAG knowledge ─────────────────────────────────────────────────────────────

def ingest_wiki_page(url: str, anime: str, source_label: str = "") -> dict:
    """
    Fetch a wiki/fandom page by URL, extract structured knowledge
    (characters, arcs, concepts, etc.) using the knowledge extraction agent,
    and upsert the results into ChromaDB.

    source_label is a short name used for the ChromaDB document metadata
    (defaults to the last path segment of the URL).
    """
    import requests
    from agents.knowledge_extraction_agent import extract_and_ingest

    label = source_label or url.rstrip("/").split("/")[-1].replace("_", " ")

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; theme-rag-builder/1.0)"},
            timeout=20,
        )
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        return {"success": False, "error": f"Failed to fetch {url}: {e}"}

    try:
        stats = extract_and_ingest(text=html, source=label, anime=anime)
    except Exception as e:
        return {"success": False, "error": f"Extraction failed: {e}"}

    return {
        "success": True,
        "anime":   anime,
        "url":     url,
        "source":  label,
        "stats":   stats,
    }
