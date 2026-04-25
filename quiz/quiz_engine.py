from retrieval.search import semantic_search
from quiz.generator import generate_mcq_from_chunk


def generate_quiz(topic, num_questions=5):
    results = semantic_search(topic, top_k=num_questions)

    quiz = []

    for r in results:
        mcq = generate_mcq_from_chunk(r)
        quiz.append(mcq)

    return quiz