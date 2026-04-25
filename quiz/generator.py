from retrieval.search import semantic_search


def generate_mcq_from_chunk(chunk):
    """
    Simple rule-based MCQ generator (fast + deterministic)
    """

    text = chunk["text"]

    # crude extraction of "fact sentence"
    sentence = text.split(".")[0]

    # naive entity extraction (you can improve later with LLM/NLP)
    correct_answer = chunk["metadata"].get("entity", "Unknown")

    question = f"Which statement best describes {correct_answer}?"

    options = [
        sentence,
        "He is a Marine Admiral",
        "He is a Warlord of the Sea",
        "He is a Revolutionary Army leader"
    ]

    return {
        "question": question,
        "options": options,
        "answer": sentence
    }