"""
Anime presets for the Character Addition Agent (MyAnimeList source).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AnimePreset:
    item_name: str
    mal_id: int


PRESETS: dict[str, AnimePreset] = {
    "one piece": AnimePreset(item_name="One Piece", mal_id=21),
    "naruto": AnimePreset(item_name="Naruto", mal_id=20),
}


def resolve_preset(item_name: str | None) -> AnimePreset:
    if not item_name:
        return PRESETS["one piece"]
    key = item_name.strip().lower()
    if key in PRESETS:
        return PRESETS[key]
    for preset in PRESETS.values():
        if preset.item_name.lower() == key:
            return preset
    raise ValueError(
        f"Unknown anime '{item_name}'. Known presets: {', '.join(p.item_name for p in PRESETS.values())}"
    )
