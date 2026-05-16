"""
Discover character page titles from a Fandom wiki hub / list pages.
"""

import time
import requests

FANDOM_API = "https://{wiki}.fandom.com/api.php"
DELAY      = 0.3

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; theme-rag-builder/1.0)"}

SKIP_PREFIXES = (
    "Chapter ",
    "Episode ",
    "List of",
    "Category:",
    "One Piece ",
    "Template:",
    "File:",
)
SKIP_SUFFIXES = (" Arc", " Saga", " Island")


def _is_character_title(title: str) -> bool:
    if "/" in title:
        return False
    if any(title.startswith(p) for p in SKIP_PREFIXES):
        return False
    if any(title.endswith(s) for s in SKIP_SUFFIXES):
        return False
    return True


def _fetch_links(wiki: str, page: str) -> list[str]:
    url = FANDOM_API.format(wiki=wiki)
    params = {"action": "parse", "page": page, "prop": "links", "format": "json"}
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        links = resp.json().get("parse", {}).get("links", [])
        return [l["*"] for l in links if l.get("ns") == 0]
    except Exception as e:
        print(f"  ⚠️  Could not fetch links for '{page}': {e}")
        return []


def discover_from_character_list(wiki: str, list_page: str) -> list[str]:
    """
    Scan a wiki character index page and its letter-range subpages
    (e.g. List of Canon Characters / Names A-E).
    """
    seen: set[str] = set()
    result: list[str] = []

    root_links = _fetch_links(wiki, list_page)
    time.sleep(DELAY)

    subpages = [p for p in root_links if p.startswith(f"{list_page}/")]
    pages_to_scan = [list_page, *subpages]

    for page in pages_to_scan:
        print(f"  📄 Scanning: {page}")
        for title in _fetch_links(wiki, page):
            if not _is_character_title(title):
                continue
            if title in seen:
                continue
            seen.add(title)
            result.append(title)
        time.sleep(DELAY)

    return result


def discover_from_hub(wiki: str, hub_page: str, character_list_page: str) -> list[str]:
    """
    Start at the wiki hub (e.g. One_Piece_Wiki), confirm the character list
  page is linked, then scrape that list.
    """
    hub_links = _fetch_links(wiki, hub_page)
    if character_list_page not in hub_links:
        print(f"  ⚠️  '{character_list_page}' not linked from '{hub_page}' — scanning list anyway")
    return discover_from_character_list(wiki, character_list_page)
