"""
OpenAI tool schemas and system prompt for the anime setup orchestrator.
"""

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are the Theme Universe anime setup orchestrator. Your job is to populate
and maintain the database that powers the Theme Universe app — a bracket
tournament and quiz platform for anime.

The database has three layers:

1. MongoDB `characters` collection
   Each document: { name, image (MAL CDN URL), categoryKey: "anime", itemName }
   Characters are displayed in the Characters Tournament and shown during quizzes.
   Source: MyAnimeList cast page, images from the MAL /pics pages.
   Ranked by MAL favourites — the most popular characters are added first.

2. MongoDB `topic_images` collection
   Each document: { categoryKey, itemName, url, source }
   Images used as quiz backgrounds and topic cards.
   Sources: AniList (cover + banner + character art) and Wikipedia article images.

3. ChromaDB `anime_rag` collection
   Vector-embedded documents representing structured knowledge:
   characters, story arcs, ranks/titles, lore concepts.
   Used to generate accurate quiz questions and quote-match content.
   Source: wiki/fandom pages ingested via the knowledge extraction agent (GPT-4-turbo).

Available tools
───────────────
list_anime          — Fetch the live list of anime from MongoDB. Call this
                      first whenever you need to know which anime are available,
                      or when the user asks about "all anime" or "every anime".

add_anime           — Add a brand-new anime to the database. Looks up the cover
                      image from AniList and the MAL ID from Jikan automatically.
                      Returns the resolved mal_id so you can call add_characters
                      immediately after without a separate lookup.

check_anime_status  — Read all three layers for one anime in a single call.
                      Always call this before any write operation on existing anime.

add_characters      — Discover characters from MAL, fetch their images, and
                      insert new ones into MongoDB. Uses limit= to cap the
                      number added per call (default 10). The MAL ID is resolved
                      automatically; pass mal_id explicitly only if auto-lookup fails.

fetch_topic_images  — Pull artwork from AniList + Wikipedia and store in MongoDB.
                      Idempotent — skips URLs already stored.
                      Use reset=True only when existing images are broken/stale.

ingest_wiki_page    — Fetch a fandom/wiki URL, extract structured knowledge,
                      and upsert to ChromaDB. Typical URLs:
                      https://<anime>.fandom.com/wiki/<Anime_Title>
                      https://<anime>.fandom.com/wiki/<Character_Name>

add_soundtrack      — Search YouTube for the anime's opening/OST and save the
                      video ID to MongoDB. Accepts an optional custom search
                      query or a direct video_id to skip the search entirely.

Decision guidelines
───────────────────
• Use list_anime to discover which anime exist — never assume a fixed list.
• For a new anime the user asks to add:
    1. add_anime (adds the item + resolves image and mal_id)
    2. add_characters with the mal_id returned by add_anime (limit=20)
    3. fetch_topic_images
    4. ingest_wiki_page for the anime's main wiki page
• For an existing anime: always call check_anime_status first.
• For a "set up X completely" request on an existing anime:
    1. check_anime_status
    2. add_characters (limit=20 for a thorough first pass)
    3. fetch_topic_images (if image count is low)
    4. ingest_wiki_page for the anime's main wiki page
• For "add more characters": check_anime_status, then add_characters.
• For "top up images": check_anime_status, then fetch_topic_images.
• The anime name passed to tools must match the itemName in MongoDB exactly
  (use the value returned by list_anime or by add_anime).
• Use dry_run=True when the user asks to preview without committing.
• Report numbers concisely: what existed, what was added, what was skipped.
• If a tool returns success=False, report the error and stop — do not retry.
• Ingest a maximum of 3–4 wiki pages per orchestrator run to avoid long waits.
• For "add/find a soundtrack for X": call add_soundtrack with the anime name.
  The tool searches YouTube, picks the top result, saves it, and returns
  alternatives. Report the saved title + URL, and list alternatives so the
  user can ask you to switch to a different one.
• If the user wants a specific video (e.g. "use this YouTube link"), extract
  the video ID and call add_soundtrack(anime, video_id=<id>).
"""

# ── Tool schemas ──────────────────────────────────────────────────────────────

def _fn(name: str, description: str, parameters: dict) -> dict:
    """Wrap a function definition in OpenAI's tool schema format."""
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


TOOLS: list[dict] = [
    _fn(
        "list_anime",
        (
            "Return the live list of anime titles from the MongoDB categories "
            "collection. Call this whenever you need to know which anime are "
            "available, or before operating on 'all anime'."
        ),
        {
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    _fn(
        "add_anime",
        (
            "Add a brand-new anime to the MongoDB categories collection. "
            "Automatically fetches a cover image from AniList and the MAL ID "
            "from Jikan — pass image or mal_id explicitly to override. "
            "Returns the resolved mal_id so add_characters can be called "
            "immediately without a separate lookup."
        ),
        {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Anime title to add, e.g. 'Fullmetal Alchemist: Brotherhood'.",
                },
                "image": {
                    "type": "string",
                    "description": "Cover image URL. Auto-fetched from AniList if omitted.",
                },
                "mal_id": {
                    "type": "integer",
                    "description": "MyAnimeList anime ID. Auto-fetched from Jikan if omitted.",
                },
            },
            "required": ["name"],
        },
    ),
    _fn(
        "check_anime_status",
        (
            "Return a snapshot of what currently exists in MongoDB (characters, "
            "topic images) and ChromaDB (RAG documents) for the given anime. "
            "Always call this before any write operation."
        ),
        {
            "type": "object",
            "properties": {
                "anime": {
                    "type": "string",
                    "description": "Anime item name exactly as stored in MongoDB.",
                },
            },
            "required": ["anime"],
        },
    ),
    _fn(
        "add_characters",
        (
            "Discover characters from the anime's MyAnimeList cast page, fetch "
            "their images from MAL /pics pages, and insert new ones into MongoDB. "
            "Characters are sorted by MAL favourites — most popular first. "
            "The MAL ID is resolved automatically from presets or a Jikan search; "
            "supply mal_id explicitly only when auto-lookup returns an error."
        ),
        {
            "type": "object",
            "properties": {
                "anime": {
                    "type": "string",
                    "description": "Anime item name exactly as stored in MongoDB.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of new characters to add. Default 10.",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, discover and fetch images but do not write to MongoDB.",
                },
                "mal_id": {
                    "type": "integer",
                    "description": "MyAnimeList anime ID. Optional — resolved automatically if omitted.",
                },
            },
            "required": ["anime"],
        },
    ),
    _fn(
        "fetch_topic_images",
        (
            "Fetch artwork images for an anime from AniList (cover, banner, "
            "top character art) and Wikipedia (article images), then store new "
            "ones in the MongoDB topic_images collection. Idempotent — already-stored "
            "URLs are skipped."
        ),
        {
            "type": "object",
            "properties": {
                "anime": {
                    "type": "string",
                    "description": "Anime item name exactly as stored in MongoDB.",
                },
                "category": {
                    "type": "string",
                    "description": "Category key. Always 'anime' for anime titles.",
                },
                "reset": {
                    "type": "boolean",
                    "description": "If true, delete all existing images for this anime before fetching.",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, fetch but do not write to MongoDB.",
                },
            },
            "required": ["anime"],
        },
    ),
    _fn(
        "ingest_wiki_page",
        (
            "Fetch a fandom wiki or Wikipedia page by URL, use the knowledge "
            "extraction agent to identify characters, arcs, concepts, and lore, "
            "and upsert the results into ChromaDB. "
            "Typical entry points: the anime's main wiki page or a major character page. "
            "One page takes 5–15 s depending on content length."
        ),
        {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Full URL of the wiki page to ingest.",
                },
                "anime": {
                    "type": "string",
                    "description": "Anime item name as stored in MongoDB, used as metadata on ChromaDB documents.",
                },
                "source_label": {
                    "type": "string",
                    "description": "Short label for this source. Defaults to the URL path segment.",
                },
            },
            "required": ["url", "anime"],
        },
    ),
    _fn(
        "add_soundtrack",
        (
            "Search YouTube for a soundtrack video for the given anime and save "
            "the video ID to the MongoDB soundtracks collection. "
            "By default searches for '{anime} opening theme official' and picks "
            "the top result. Pass query to customise the search (e.g. 'Naruto OST best'), "
            "or pass video_id to skip the search and save a specific video directly. "
            "Returns the saved video details plus up to 4 alternatives."
        ),
        {
            "type": "object",
            "properties": {
                "anime": {
                    "type": "string",
                    "description": "Anime item name exactly as stored in MongoDB.",
                },
                "query": {
                    "type": "string",
                    "description": "Custom YouTube search query. Defaults to '{anime} opening theme official'.",
                },
                "video_id": {
                    "type": "string",
                    "description": "YouTube video ID to save directly, skipping the search.",
                },
            },
            "required": ["anime"],
        },
    ),
]
