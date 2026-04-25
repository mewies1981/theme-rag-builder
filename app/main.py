from scraper.local_loader import load_html_files
from scraper.page_parser import extract_sections
from scraper.chunk_builder import build_chunks
from scraper.type_classifier import infer_type  # NEW (important)

import chromadb
from ingestion.ingest_to_chroma import get_or_create_collection, ingest_chunks


def run_pipeline():
    files = load_html_files("./htmls/one_piece")

    print(f"📁 Files loaded: {len(files)}")

    all_chunks = []

    for f in files:
        print(f"\n🔹 Processing file: {f['file']}")

        # STEP 1: Extract sections
        sections = extract_sections(f["html"])
        print(f"   📄 Sections extracted: {len(sections)}")

        if not sections:
            print("   ⚠️ No sections found, skipping file")
            continue

        # STEP 2: Build enriched chunks (STRUCTURED RAG DATA)
        chunks = build_chunks(
            sections,
            anime="One Piece",
            entity_name=f["file"].replace(".html", "")
        )

        # STEP 3: ENRICH CHUNKS (IMPORTANT NEW STEP)
        enriched_chunks = []

        for c in chunks:
            text = c["document"]

            chunk = {
                "id": c["id"],
                "document": text,
                "metadata": {
                    "anime": "One Piece",

                    # 🔥 KEY IMPROVEMENT: semantic classification
                    "type": infer_type(text),

                    # entity reference (character / arc / fruit / org)
                    "entity": c.get("metadata", {}).get("entity", f["file"]),

                    # optional enrichment
                    "tags": c.get("metadata", {}).get("tags", [])
                }
            }

            enriched_chunks.append(chunk)

        print(f"   🧩 Chunks created: {len(enriched_chunks)}")

        if enriched_chunks:
            all_chunks.extend(enriched_chunks)

    print(f"\n✅ TOTAL CHUNKS GENERATED: {len(all_chunks)}")

    return all_chunks


if __name__ == "__main__":
    chunks = run_pipeline()

    if not chunks:
        print("❌ No chunks generated — stopping ingestion")
        exit(0)

    # 🧠 Persistent vector DB (CRITICAL)
    client = chromadb.PersistentClient(path="./chroma_db")

    collection = get_or_create_collection(client)

    ingest_chunks(chunks, collection)

    print("🚀 Ingestion completed successfully")