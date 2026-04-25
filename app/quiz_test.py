from quiz.quiz_engine import generate_quiz
import json

topic = "Monkey D. Luffy"

quiz = generate_quiz(topic, num_questions=5)

print("\n🎯 ONE PIECE QUIZ:\n")

for i, q in enumerate(quiz):
    print(f"Q{i+1}: {q['question']}")
    
    for idx, opt in enumerate(q["options"]):
        print(f"   {chr(65+idx)}. {opt}")

    print(f"\n✅ Answer: {q['answer']}")
    print("-" * 50)