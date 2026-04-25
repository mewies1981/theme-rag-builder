"""
Page Discoverer — Fandom MediaWiki API
---------------------------------------
Discovers page titles from fandom wiki categories automatically,
so run_extraction.py never needs a hardcoded page list.

Supports full pagination — retrieves ALL members of a category,
not just the first batch.

Usage:
    from scraper.page_discoverer import discover_pages

    titles = discover_pages(wiki="onepiece", categories=ONEPIECE_CATEGORIES)
"""

import time
import requests

FANDOM_API  = "https://{wiki}.fandom.com/api.php"
BATCH_LIMIT = 500   # max allowed by MediaWiki API
DELAY       = 0.5   # seconds between pagination requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; anime-rag-builder/1.0)"
}

# Categories confirmed to work on onepiece.fandom.com
ONEPIECE_CATEGORIES = [
    "Straw Hat Pirates",
    "Devil Fruits",
    "Story Arcs",
    "Story Sagas",
    "Four Emperors",
    "Seven Warlords of the Sea",
    "Marines",
    "Revolutionary Army",
    "Whitebeard Pirates",
]


def _fetch_category_members(wiki: str, category: str) -> list[str]:
    """
    Fetch all article titles in a wiki category, following pagination tokens.
    Returns a list of page title strings (namespace 0 only).
    """
    url = FANDOM_API.format(wiki=wiki)
    titles = []
    cont_token = None

    while True:
        params = {
            "action":      "query",
            "list":        "categorymembers",
            "cmtitle":     f"Category:{category}",
            "cmlimit":     BATCH_LIMIT,
            "cmnamespace": 0,           # articles only, no sub-categories
            "cmtype":      "page",
            "format":      "json",
        }
        if cont_token:
            params["cmcontinue"] = cont_token

        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  ⚠️  Error fetching category '{category}': {e}")
            break

        data = resp.json()
        members = data.get("query", {}).get("categorymembers", [])
        titles.extend(m["title"] for m in members)

        # Check for continuation
        cont = data.get("continue", {})
        cont_token = cont.get("cmcontinue")
        if not cont_token:
            break

        time.sleep(DELAY)

    return titles


def discover_pages(
    wiki: str = "onepiece",
    categories: list[str] = None,
    exclude: set[str] = None,
) -> list[str]:
    """
    Discover all page titles across the given categories.

    Args:
        wiki:       Fandom subdomain (e.g. "onepiece").
        categories: List of category names to scan. Defaults to ONEPIECE_CATEGORIES.
        exclude:    Set of titles to skip (e.g. already-processed pages).

    Returns:
        Deduplicated list of new page titles, preserving discovery order.
    """
    if categories is None:
        categories = ONEPIECE_CATEGORIES
    if exclude is None:
        exclude = set()

    seen   = set(exclude)
    result = []

    for cat in categories:
        print(f"  🔍 Scanning category: {cat}")
        members = _fetch_category_members(wiki, cat)
        new = [t for t in members if t not in seen]
        for t in new:
            seen.add(t)
            result.append(t)
        print(f"      → {len(members)} pages found, {len(new)} new")

    return result
