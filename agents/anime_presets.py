"""
Anime presets for the Character Addition Agent (MyAnimeList source).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AnimePreset:
    item_name: str
    mal_id: int


PRESETS: dict[str, AnimePreset] = {
    "one piece":          AnimePreset(item_name="One Piece",          mal_id=21),
    "naruto":             AnimePreset(item_name="Naruto",             mal_id=20),
    "steins;gate":        AnimePreset(item_name="Steins;Gate",        mal_id=9253),
    "fruits basket":      AnimePreset(item_name="Fruits Basket",      mal_id=38680),
    "attack on titan":    AnimePreset(item_name="Attack on Titan",    mal_id=16498),
    "death note":         AnimePreset(item_name="Death Note",         mal_id=1535),
    "fmab":               AnimePreset(item_name="FMAB",               mal_id=5114),
    "one punch man":      AnimePreset(item_name="One Punch Man",      mal_id=30276),
    "demon slayer":       AnimePreset(item_name="Demon Slayer",       mal_id=38000),
    "my hero academia":   AnimePreset(item_name="My Hero Academia",   mal_id=31964),
    "hunter x hunter":    AnimePreset(item_name="Hunter x Hunter",    mal_id=11061),
    "spy x family":       AnimePreset(item_name="Spy x Family",       mal_id=50265),
    "promised neverland": AnimePreset(item_name="Promised Neverland", mal_id=37779),
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
        f"Unknown anime '{item_name}'. "
        f"Known presets: {', '.join(p.item_name for p in PRESETS.values())}"
    )
