"""
Fandom character images — ?file= wiki page pattern
--------------------------------------------------
For each character, builds a URL like:
  https://onepiece.fandom.com/wiki/Abdullah?file=Abdullah+Anime+Infobox.png

The infobox filename comes from the character page HTML; the image URL is
resolved via the wiki File API (same asset as the ?file= lightbox view).
"""

import time
from dataclasses import dataclass
from urllib.parse import quote, quote_plus

import requests
from bs4 import BeautifulSoup

FANDOM_API  = "https://{wiki}.fandom.com/api.php"
FANDOM_WIKI = "https://{wiki}.fandom.com/wiki/{title}"
DELAY       = 0.3

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; theme-rag-builder/1.0)"}


@dataclass
class CharacterImage:
    url: str
    file_name: str
    file_page_url: str


def wiki_page_url(wiki: str, character_name: str) -> str:
    slug = quote(character_name.replace(" ", "_"), safe="")
    return FANDOM_WIKI.format(wiki=wiki, title=slug)


def wiki_page_with_file_url(wiki: str, character_name: str, file_name: str) -> str:
    """Public wiki URL with ?file= query (Fandom lightbox / file viewer)."""
    base = wiki_page_url(wiki, character_name)
    return f"{base}?file={quote_plus(file_name)}"


def _pick_infobox_file(file_keys: list[str]) -> str | None:
    if not file_keys:
        return None
    anime = [k for k in file_keys if "Anime" in k and "Manga" not in k]
    pool = anime or file_keys
    for hint in ("Post Timeskip", "Pre Timeskip", "Anime"):
        for key in pool:
            if hint in key:
                return key
    return pool[0]


def _infobox_file_keys(soup: BeautifulSoup) -> list[str]:
    pi = soup.select_one("aside.portable-infobox, .portable-infobox")
    if not pi:
        return []
    keys = []
    for img in pi.select("img[data-image-key]"):
        key = img.get("data-image-key", "")
        if key and "Infobox" in key and key not in keys:
            keys.append(key)
    return keys


def _fetch_character_html(character_name: str, wiki: str) -> str | None:
    try:
        resp = requests.get(
            FANDOM_API.format(wiki=wiki),
            params={"action": "parse", "page": character_name, "prop": "text", "format": "json"},
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("parse", {}).get("text", {}).get("*", "") or None
    except Exception as e:
        print(f"    ⚠️  Could not load page for '{character_name}': {e}")
        return None


def _resolve_file_image_url(file_name: str, wiki: str, referer: str) -> str | None:
    try:
        resp = requests.get(
            FANDOM_API.format(wiki=wiki),
            params={
                "action":  "query",
                "titles":  f"File:{file_name}",
                "prop":    "imageinfo",
                "iiprop":  "url",
                "format":  "json",
            },
            headers={**HEADERS, "Referer": referer},
            timeout=15,
        )
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            info = page.get("imageinfo", [])
            if info:
                return info[0].get("url")
    except Exception as e:
        print(f"    ⚠️  File API error for '{file_name}': {e}")
    return None


def scrape_image(character_name: str, wiki: str) -> CharacterImage | None:
    html = _fetch_character_html(character_name, wiki)
    if not html:
        return None

    file_name = _pick_infobox_file(_infobox_file_keys(BeautifulSoup(html, "lxml")))
    if not file_name:
        return None

    file_page_url = wiki_page_with_file_url(wiki, character_name, file_name)
    print(f"  🔍 File page URL: {file_page_url}")
    image_url = _resolve_file_image_url(file_name, wiki, referer=file_page_url)
    print(f"  🔍 Image URL: {image_url}")
    if not image_url:
        print(f"    ⚠️  No image URL found for '{character_name}'")
        return None
    else:
        print(f"  ✅ Image URL found for '{character_name}'")
    return CharacterImage(
        url=image_url,
        file_name=file_name,
        file_page_url=file_page_url,
    )


def fetch_images(titles: list[str], wiki: str) -> dict[str, CharacterImage | None]:
    result: dict[str, CharacterImage | None] = {}
    for i, title in enumerate(titles):
        result[title] = scrape_image(title, wiki)
        if i < len(titles) - 1:
            time.sleep(DELAY)
    return result
