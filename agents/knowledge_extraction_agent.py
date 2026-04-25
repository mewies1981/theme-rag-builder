"""
Knowledge Extraction Agent
--------------------------
Reads raw HTML or plain text from wiki/fandom pages, uses Claude to
identify and extract structured knowledge, then upserts it into the
ChromaDB RAG knowledge base (collection: anime_rag).

Extracted entity types:
  - characters
  - arcs
  - devil_fruits
  - ranks
  - concepts

Usage:

    # Extract only (returns structured dict)
    from agents.knowledge_extraction_agent import extract_knowledge
    result = extract_knowledge(text="...", source="Monkey D. Luffy", anime="One Piece")

    # Extract + ingest into ChromaDB in one call
    from agents.knowledge_extraction_agent import extract_and_ingest
    stats = extract_and_ingest(text="...", source="Monkey D. Luffy", anime="One Piece")
    # stats = {"characters": 3, "arcs": 1, "devil_fruits": 1, "ranks": 2, "concepts": 4, "total": 11}
"""

import json
import os
import re
import sys
from pathlib import Path
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI
import chromadb

# Allow imports from project root (config, ingestion, …)
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config import DB_PATH, COLLECTION_NAME, EMBED_MODEL
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

load_dotenv(_PROJECT_ROOT / ".env")

MODEL = "gpt-4-turbo"

SYSTEM_PROMPT = """\
You are a knowledge extraction agent specialised in anime wikis.

Given a passage of text from an anime wiki page, extract every piece of
structured knowledge you can find and return it as a single JSON object
with these five keys:

  "characters"   – list of characters mentioned
  "arcs"         – list of story arcs or sagas mentioned
  "devil_fruits" – list of Devil Fruits mentioned (One Piece specific)
  "ranks"        – list of titles, ranks, or positions held by characters
  "concepts"     – list of organisations, techniques, places, or other lore concepts

Each item must be an object. Use these schemas:

  characters:   { "name": str, "role": str, "description": str }
  arcs:         { "name": str, "description": str }
  devil_fruits: { "name": str, "type": str, "user": str, "ability": str }
  ranks:        { "title": str, "holder": str, "organization": str }
  concepts:     { "name": str, "category": str, "description": str }

Rules:
- Only include entities that are clearly present in the provided text.
- If a field is unknown, use an empty string "".
- Return ONLY valid JSON — no markdown, no explanation, no preamble.
- If a key has no entries, return an empty list [].
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _strip_html(raw: str) -> str:
    soup = BeautifulSoup(raw, "lxml")
    return soup.get_text(separator="\n", strip=True)


def _is_html(text: str) -> bool:
    return "<html" in text[:500].lower() or "<body" in text[:500].lower()


def _slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")[:80]


def _make_id(anime: str, entity_type: str, name: str) -> str:
    return f"{_slugify(anime)}__{entity_type}__{_slugify(name)}"


# ── Entity → ChromaDB document converters ─────────────────────────────────────

def _character_to_chunk(entity: dict, anime: str, source: str) -> dict:
    name = entity.get("name", "")
    text = f"Character: {name}. Role: {entity.get('role', '')}. {entity.get('description', '')}"
    return {
        "id":       _make_id(anime, "character", name),
        "document": text.strip(),
        "metadata": {
            "anime":       anime,
            "source":      source,
            "entity_type": "character",
            "name":        name,
        },
    }


def _arc_to_chunk(entity: dict, anime: str, source: str) -> dict:
    name = entity.get("name", "")
    text = f"Story Arc: {name}. {entity.get('description', '')}"
    return {
        "id":       _make_id(anime, "arc", name),
        "document": text.strip(),
        "metadata": {
            "anime":       anime,
            "source":      source,
            "entity_type": "arc",
            "name":        name,
        },
    }


def _devil_fruit_to_chunk(entity: dict, anime: str, source: str) -> dict:
    name = entity.get("name", "")
    text = (
        f"Devil Fruit: {name} ({entity.get('type', '')} type). "
        f"User: {entity.get('user', '')}. "
        f"Ability: {entity.get('ability', '')}"
    )
    return {
        "id":       _make_id(anime, "devil_fruit", name),
        "document": text.strip(),
        "metadata": {
            "anime":       anime,
            "source":      source,
            "entity_type": "devil_fruit",
            "name":        name,
            "user":        entity.get("user", ""),
            "type":        entity.get("type", ""),
        },
    }


def _rank_to_chunk(entity: dict, anime: str, source: str) -> dict:
    title = entity.get("title", "")
    text = (
        f"Rank/Title: {title}. "
        f"Held by: {entity.get('holder', '')}. "
        f"Organization: {entity.get('organization', '')}"
    )
    return {
        "id":       _make_id(anime, "rank", f"{title}_{entity.get('holder', '')}"),
        "document": text.strip(),
        "metadata": {
            "anime":        anime,
            "source":       source,
            "entity_type":  "rank",
            "title":        title,
            "holder":       entity.get("holder", ""),
            "organization": entity.get("organization", ""),
        },
    }


def _concept_to_chunk(entity: dict, anime: str, source: str) -> dict:
    name = entity.get("name", "")
    text = f"{entity.get('category', 'Concept')}: {name}. {entity.get('description', '')}"
    return {
        "id":       _make_id(anime, "concept", name),
        "document": text.strip(),
        "metadata": {
            "anime":       anime,
            "source":      source,
            "entity_type": "concept",
            "name":        name,
            "category":    entity.get("category", ""),
        },
    }


_CONVERTERS = {
    "characters":   _character_to_chunk,
    "arcs":         _arc_to_chunk,
    "devil_fruits": _devil_fruit_to_chunk,
    "ranks":        _rank_to_chunk,
    "concepts":     _concept_to_chunk,
}


def _to_chunks(knowledge: dict, anime: str, source: str) -> list[dict]:
    """Convert extracted knowledge dict into a flat list of ChromaDB chunk dicts."""
    chunks = []
    for key, converter in _CONVERTERS.items():
        for entity in knowledge.get(key, []):
            name = entity.get("name") or entity.get("title", "")
            if not name:
                continue
            chunk = converter(entity, anime, source)
            if chunk["document"]:
                chunks.append(chunk)
    return chunks


def _get_collection() -> chromadb.Collection:
    ef = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
    client = chromadb.PersistentClient(path=DB_PATH)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


# ── Public API ────────────────────────────────────────────────────────────────

def extract_knowledge(text: str, source: str = "", anime: str = "") -> dict:
    """
    Extract structured knowledge from raw HTML or plain text.

    Returns a dict with keys: characters, arcs, devil_fruits, ranks, concepts.
    Does NOT write to ChromaDB — use extract_and_ingest() for that.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY not set in environment or .env file.")

    clean_text = _strip_html(text) if _is_html(text) else text
    if len(clean_text) > 12000:
        clean_text = clean_text[:12000] + "\n[truncated]"

    context_note = ""
    if anime:
        context_note = f"Anime: {anime}\n"
    if source:
        context_note += f"Source page: {source}\n"

    user_message = f"{context_note}\n---\n{clean_text}"

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=2048,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
    )

    raw_output = response.choices[0].message.content.strip()

    try:
        result = json.loads(raw_output)
    except json.JSONDecodeError as e:
        raise ValueError(f"Agent returned invalid JSON: {e}\n\nRaw output:\n{raw_output}")

    for key in ("characters", "arcs", "devil_fruits", "ranks", "concepts"):
        result.setdefault(key, [])

    return result


def extract_and_ingest(
    text: str,
    source: str = "",
    anime: str = "",
    collection: chromadb.Collection = None,
) -> dict:
    """
    Extract structured knowledge and upsert it into the ChromaDB RAG knowledge base.

    Args:
        text:       Raw HTML or plain text.
        source:     Source label (e.g. file name or character name).
        anime:      Anime name (e.g. "One Piece").
        collection: Optional pre-opened ChromaDB collection. Opens one if not provided.

    Returns:
        Stats dict: { "characters": N, "arcs": N, "devil_fruits": N,
                      "ranks": N, "concepts": N, "total": N }
    """
    knowledge = extract_knowledge(text=text, source=source, anime=anime)
    chunks = _to_chunks(knowledge, anime=anime, source=source)

    if not chunks:
        print(f"  ⚠️  No entities extracted from '{source}'")
        return {k: 0 for k in ("characters", "arcs", "devil_fruits", "ranks", "concepts", "total")}

    col = collection or _get_collection()
    col.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["document"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )

    stats = {k: len(knowledge.get(k, [])) for k in ("characters", "arcs", "devil_fruits", "ranks", "concepts")}
    stats["total"] = sum(stats.values())

    print(f"  ✅ '{source}': upserted {stats['total']} entities "
          f"(chars={stats['characters']}, arcs={stats['arcs']}, "
          f"fruits={stats['devil_fruits']}, ranks={stats['ranks']}, "
          f"concepts={stats['concepts']})")

    return stats
