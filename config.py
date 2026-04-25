from pathlib import Path

# Absolute path so any project can point here regardless of working directory
DB_PATH         = str(Path(__file__).parent / "chroma_db")
COLLECTION_NAME = "anime_rag"
EMBED_MODEL     = "all-MiniLM-L6-v2"
