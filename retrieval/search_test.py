from retrieval.search import semantic_search

query = "Who is Monkey D. Luffy?"

results = semantic_search(query)

print("\n🔍 SEARCH RESULTS:\n")

for r in results:
    print("ID:", r["id"])
    print("TEXT:", r["text"][:200])
    print("SCORE:", r["score"])
    print("-" * 50)