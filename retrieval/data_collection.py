import chromadb
from config import DB_PATH, COLLECTION_NAME

client = chromadb.PersistentClient(path=DB_PATH)

collection = client.get_or_create_collection(
    name=COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"}
)

print("TOTAL ITEMS:", collection.count())