import chromadb


def semantic_search(query, top_k=5):
    client = chromadb.PersistentClient(path="./chroma_db")

    collection = client.get_or_create_collection(
        name="anime_rag",
        metadata={"hnsw:space": "cosine"}
    )

    results = collection.query(
        query_texts=[query],
        n_results=top_k
    )

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    ids = results.get("ids", [[]])[0]
    distances = results.get("distances", [[]])[0]

    output = []

    for i in range(len(docs)):
        output.append({
            "id": ids[i],
            "text": docs[i],
            "metadata": metas[i],
            "score": distances[i]
        })

    return output