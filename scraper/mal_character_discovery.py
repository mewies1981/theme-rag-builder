"""
MyAnimeList character discovery
-------------------------------
Scrapes only characters listed in the anime's official cast table, e.g.
https://myanimelist.net/anime/21/One_Piece/characters
"""

import re
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

MAL_ANIME = "https://myanimelist.net/anime/{mal_id}"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}
ROLE_PATTERN = re.compile(r"\b(Main|Supporting|Background)\b")
FAVORITES_PATTERN = re.compile(r"([\d,]+)\s+Favorites?", re.I)


@dataclass(frozen=True)
class MalCharacter:
    mal_id: int
    slug: str
    name: str
    role: str = ""
    favorites: int = 0

    @property
    def pics_url(self) -> str:
        return f"https://myanimelist.net/character/{self.mal_id}/{self.slug}/pics"

    @property
    def profile_url(self) -> str:
        return f"https://myanimelist.net/character/{self.mal_id}/{self.slug}"


def normalize_mal_name(name: str) -> str:
    """MAL link text uses 'Family, Given' — store as 'Family Given' for MongoDB."""
    return re.sub(r",\s*", " ", name).strip()


def _parse_character_row(table) -> MalCharacter | None:
    """Extract one cast entry from a js-anime-character-table row."""
    links = table.select('a[href*="/character/"]')
    if not links:
        return None

    name_link = next(
        (a for a in links if (a.get("title") or a.get_text(strip=True)).strip()),
        links[0],
    )
    match = re.search(r"/character/(\d+)/([^/?#]+)", name_link["href"])
    if not match:
        return None

    raw_name = (name_link.get("title") or name_link.get_text(strip=True)).strip()
    if not raw_name:
        return None

    row_text = table.get_text(" ", strip=True)

    role = ""
    role_match = ROLE_PATTERN.search(row_text)
    if role_match:
        role = role_match.group(1)

    favorites = 0
    fav_match = FAVORITES_PATTERN.search(row_text)
    if fav_match:
        favorites = int(fav_match.group(1).replace(",", ""))

    return MalCharacter(
        mal_id=int(match.group(1)),
        slug=match.group(2),
        name=normalize_mal_name(raw_name),
        role=role,
        favorites=favorites,
    )


def _resolve_characters_page_url(mal_anime_id: int) -> str | None:
    """MAL requires the titled URL (e.g. /anime/21/One_Piece/characters) for the full cast table."""
    anime_url = MAL_ANIME.format(mal_id=mal_anime_id)
    try:
        resp = requests.get(anime_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ⚠️  Could not load {anime_url}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    for anchor in soup.select("a[href]"):
        href = urljoin(anime_url, anchor["href"])
        if re.match(rf"https://myanimelist\.net/anime/{mal_anime_id}/[^/]+/characters$", href):
            return href
    return None


def discover_characters(mal_anime_id: int) -> list[MalCharacter]:
    """
    Return characters from the selected anime's cast table only
    (not sidebar links, staff, or unrelated series).
    """
    page_url = _resolve_characters_page_url(mal_anime_id)
    if not page_url:
        print(f"  ⚠️  Could not find characters page for anime {mal_anime_id}")
        return []

    try:
        resp = requests.get(page_url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ⚠️  Could not load {page_url}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    container = soup.select_one(".js-anime-character-container")
    if not container:
        print("  ⚠️  Cast table not found on page — no characters discovered")
        return []

    seen: set[int] = set()
    result: list[MalCharacter] = []

    for table in container.select(".js-anime-character-table"):
        char = _parse_character_row(table)
        if not char or char.mal_id in seen:
            continue
        seen.add(char.mal_id)
        result.append(char)

    result.sort(key=lambda c: c.favorites, reverse=True)
    return result


def appears_in_anime(character: MalCharacter, mal_anime_id: int) -> bool:
    """
    Confirm the character's MAL profile lists the selected anime with a cast role.
    Filters out sidebar / crossover links that are not part of this anime's cast.
    """
    try:
        resp = requests.get(character.profile_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception:
        return False

    soup = BeautifulSoup(resp.text, "lxml")
    for anchor in soup.select('a[href^="https://myanimelist.net/anime/"]'):
        match = re.search(r"/anime/(\d+)/", anchor["href"])
        if not match or int(match.group(1)) != mal_anime_id:
            continue
        row = anchor.find_parent("tr") or anchor.find_parent("td")
        row_text = row.get_text(" ", strip=True) if row else anchor.get_text(" ", strip=True)
        if ROLE_PATTERN.search(row_text):
            return True
    return False
