def infer_type(text: str):

    t = text.lower()

    if "devil fruit" in t or "paramecia" in t:
        return "devil_fruit"

    if "pirates" in t or "captain" in t or "marine" in t:
        return "character"

    if "arc" in t or "saga" in t:
        return "arc"

    if "organization" in t or "government" in t:
        return "organization"

    if '"' in text or "said" in t:
        return "quote"

    return "general"