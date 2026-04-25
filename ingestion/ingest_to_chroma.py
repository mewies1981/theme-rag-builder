import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from config import DB_PATH, COLLECTION_NAME, EMBED_MODEL


def get_client():
    return chromadb.PersistentClient(path=DB_PATH)


def get_or_create_collection(client):
    ef = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def ingest_chunks(chunks, collection):
    ids = []
    documents = []
    metadatas = []

    for chunk in chunks:
        ids.append(chunk["id"])
        documents.append(chunk["document"])
        metadatas.append(chunk.get("metadata", {}))

    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )

    print(f"✅ Successfully ingested {len(ids)} chunks")
