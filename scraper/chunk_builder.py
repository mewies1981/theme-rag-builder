from scraper.type_classifier import infer_type


def build_chunks(sections, anime, entity_name):

    chunks = []

    for i, sec in enumerate(sections):

        text = sec["text"]

        chunk = {
            "id": f"{entity_name}_{i}",
            "document": text,
            "metadata": {
                "anime": anime,
                "entity": entity_name,
                "type": infer_type(text),   # NEW
            }
        }

        chunks.append(chunk)

    return chunks