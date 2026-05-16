"""
Dispatches tool_use blocks from Claude to the corresponding tool functions.
"""

from tools.anime_db_tools import (
    list_anime,
    add_anime,
    check_anime_status,
    add_characters,
    fetch_topic_images,
    ingest_wiki_page,
)

_REGISTRY = {
    "list_anime":         list_anime,
    "add_anime":          add_anime,
    "check_anime_status": check_anime_status,
    "add_characters":     add_characters,
    "fetch_topic_images": fetch_topic_images,
    "ingest_wiki_page":   ingest_wiki_page,
}


def execute_tool(name: str, tool_input: dict) -> dict:
    fn = _REGISTRY.get(name)
    if fn is None:
        return {"success": False, "error": f"Unknown tool: '{name}'"}
    try:
        return fn(**tool_input)
    except Exception as e:
        return {"success": False, "error": f"{type(e).__name__}: {e}"}
