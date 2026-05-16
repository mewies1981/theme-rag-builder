"""
MyAnimeList character pictures
------------------------------
Scrapes the first character image from a /pics page, e.g.
https://myanimelist.net/character/40/Luffy_Monkey_D/pics

Only returns an image when the character is verified to appear in the
selected anime (see mal_character_discovery.appears_in_anime).
"""

import re
import time
from dataclasses import dataclass

import requests

from scraper.mal_character_discovery import MalCharacter, appears_in_anime

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}
IMAGE_PATTERN = re.compile(r"https://myanimelist\.net/images/characters/\d+/\d+\.jpg")
DELAY = 1.0


@dataclass
class CharacterImage:
    url: str
    pics_page_url: str


def scrape_image(character: MalCharacter, mal_anime_id: int) -> CharacterImage | None:
    if not appears_in_anime(character, mal_anime_id):
        print(f"    ⚠️  Skipping '{character.name}' — not in anime {mal_anime_id} cast")
        return None

    pics_url = character.pics_url
    try:
        resp = requests.get(pics_url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"    ⚠️  Could not load {pics_url}: {e}")
        return None

    matches = IMAGE_PATTERN.findall(resp.text)
    if not matches:
        return None

    return CharacterImage(url=matches[0], pics_page_url=pics_url)


def fetch_images(
    characters: list[MalCharacter],
    mal_anime_id: int,
) -> dict[str, CharacterImage | None]:
    """Return map of display name → image (verified cast members only)."""
    result: dict[str, CharacterImage | None] = {}
    for i, char in enumerate(characters):
        result[char.name] = scrape_image(char, mal_anime_id)
        if i < len(characters) - 1:
            time.sleep(DELAY)
    return result
