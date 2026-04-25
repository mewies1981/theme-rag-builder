"""
Run the Knowledge Extraction Agent — discovers pages from the Fandom wiki
automatically and ingests extracted entities into the ChromaDB RAG knowledge base.

Already-processed pages are skipped automatically (checked via ChromaDB metadata).
New pages added to wiki categories are picked up on every run.
Use --force to re-process all pages.

Usage:
    PYTHONPATH=. venv/bin/python3 app/run_extraction.py
    PYTHONPATH=. venv/bin/python3 app/run_extraction.py --anime "One Piece" --wiki onepiece
    PYTHONPATH=. venv/bin/python3 app/run_extraction.py --force
    PYTHONPATH=. venv/bin/python3 app/run_extraction.py --limit 26
"""

import argparse
from scraper.web_fetcher import fetch_pages
from scraper.page_discoverer import discover_pages, ONEPIECE_CATEGORIES
from agents.knowledge_extraction_agent import extract_and_ingest, _get_collection

WIKI_MAP = {
    "One Piece": ("onepiece", ONEPIECE_CATEGORIES),
}


def _already_processed(collection, anime: str) -> set[str]:
    """Return the set of source page titles already in the collection for this anime."""
    results = collection.get(where={"anime": anime}, include=["metadatas"])
    sources = {m["source"] for m in results.get("metadatas", []) if m.get("source")}
    return sources


def run(anime: str, force: bool = False, limit: int = None):
    config = WIKI_MAP.get(anime)
    if not config:
        print(f"No wiki config for '{anime}'. Add it to WIKI_MAP in run_extraction.py.")
        return

    wiki, categories = config
    collection = _get_collection()

    print(f"\n🤖 Knowledge Extraction Agent — {anime}")

    # Discover all available pages from wiki categories
    print(f"\n📡 Discovering pages from {wiki}.fandom.com categories...")
    already_done = set() if force else _already_processed(collection, anime)
    pending = discover_pages(wiki=wiki, categories=categories, exclude=already_done)

    if not pending:
        print("\n✅ All discovered pages already processed. Nothing to do.")
        print("   Add new categories to the discoverer or use --force to re-process.")
        return

    if force:
        print(f"\n⚡ --force enabled: re-processing all {len(pending)} discovered pages.")
    else:
        print(f"\n⏭️  Skipping {len(already_done)} already-processed page(s).")
        print(f"📋 {len(pending)} new page(s) to process.")

    # Apply batch limit (0 = no limit)
    if limit and limit > 0 and len(pending) > limit:
        print(f"🔢 --limit {limit}: processing first {limit} of {len(pending)} new pages.")
        pending = pending[:limit]

    # Fetch wikitext for all pending pages
    print(f"\n🌐 Fetching {len(pending)} page(s)...\n")
    pages = fetch_pages(pending, wiki=wiki)
    print(f"\n✅ Fetched {len(pages)}/{len(pending)} pages\n")

    # Extract + ingest
    totals = {"characters": 0, "arcs": 0, "devil_fruits": 0, "ranks": 0, "concepts": 0, "total": 0}

    for page in pages:
        print(f"🔹 Extracting: {page['title']}")
        stats = extract_and_ingest(
            text=page["text"],
            source=page["title"],
            anime=anime,
            collection=collection,
        )
        for k in totals:
            totals[k] += stats.get(k, 0)

    print(f"\n{'='*60}")
    print(f"✅ Done — {anime}")
    print(f"   Characters  : {totals['characters']}")
    print(f"   Arcs        : {totals['arcs']}")
    print(f"   Devil Fruits: {totals['devil_fruits']}")
    print(f"   Ranks       : {totals['ranks']}")
    print(f"   Concepts    : {totals['concepts']}")
    print(f"   Total upserted: {totals['total']}")
    print(f"\n📦 ChromaDB '{collection.name}' now has {collection.count()} documents")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--anime", default="One Piece")
    parser.add_argument("--force", action="store_true", help="Re-process all pages even if already ingested")
    parser.add_argument("--limit", type=int, default=10, help="Max number of new pages to process per run (default: 10)")
    args = parser.parse_args()
    run(args.anime, force=args.force, limit=args.limit)
