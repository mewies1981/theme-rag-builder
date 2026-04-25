"""
Web Fetcher — Fandom MediaWiki API
-----------------------------------
Fetches wiki page content for anime characters, arcs, devil fruits, etc.
from the One Piece fandom wiki using the MediaWiki API (no Cloudflare issues).

The API returns raw wikitext which Claude handles well for knowledge extraction.

Usage:
    from scraper.web_fetcher import fetch_page, fetch_pages

    text = fetch_page("Monkey D. Luffy", wiki="onepiece")
    pages = fetch_pages(["Roronoa Zoro", "Nami", "Sanji"], wiki="onepiece")
"""

import time
import requests

FANDOM_API = "https://{wiki}.fandom.com/api.php"
DELAY = 1.0  # seconds between requests to be polite

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; anime-rag-builder/1.0)"
}


def fetch_page(title: str, wiki: str = "onepiece") -> str | None:
    """
    Fetch the wikitext content of a single page from a Fandom wiki.

    Args:
        title: Page title (e.g. "Monkey D. Luffy", "Gomu Gomu no Mi")
        wiki:  Fandom subdomain (default: "onepiece")

    Returns:
        Raw wikitext string, or None if the page doesn't exist.
    """
    url = FANDOM_API.format(wiki=wiki)
    params = {
        "action":  "query",
        "titles":  title,
        "prop":    "revisions",
        "rvprop":  "content",
        "rvslots": "main",
        "format":  "json",
    }

    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  ⚠️  Network error fetching '{title}': {e}")
        return None

    data = resp.json()
    pages = data.get("query", {}).get("pages", {})

    for pid, page in pages.items():
        if pid == "-1":
            print(f"  ⚠️  Page not found: '{title}'")
            return None
        revisions = page.get("revisions", [])
        if not revisions:
            return None
        content = revisions[0].get("slots", {}).get("main", {}).get("*", "")
        return content

    return None


def fetch_pages(titles: list[str], wiki: str = "onepiece") -> list[dict]:
    """
    Fetch multiple pages sequentially with a polite delay between requests.

    Returns:
        List of dicts: [{ "title": str, "text": str }]
        Pages that 404 or error are skipped.
    """
    results = []
    for i, title in enumerate(titles):
        print(f"  🌐 Fetching ({i+1}/{len(titles)}): {title}")
        text = fetch_page(title, wiki=wiki)
        if text:
            results.append({"title": title, "text": text})
        if i < len(titles) - 1:
            time.sleep(DELAY)
    return results
