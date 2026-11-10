from intent_extractor import extract_preferences

test_cases = [
    {
        "name": "Weekend outing",
        "input": (
            "I have 4 hours on Saturday, ₹1,500 per person, "
            "and want something fun with friends in Mumbai."
        ),
    },
    {
        "name": "Couple's plan",
        "input": (
            "Plan a romantic evening in Bandra with my "
            "partner. Budget ₹2,000 per person."
        ),
    },
    {
        "name": "At-home activity",
        "input": (
            "I'm bored and don't want to leave home. "
            "Suggest something creative."
        ),
    },
    {
        "name": "Multiple activities",
        "input": (
            "Plan a Sunday with breakfast, a movie, "
            "and dinner in Mumbai."
        ),
    },
    {
        "name": "Vague request",
        "input": "I want to do something interesting today.",
    },
]

for i, case in enumerate(test_cases, start=1):
    print(f"\nTEST {i}: {case['name']}")
    print("Input:", case["input"])

    try:
        result = extract_preferences(case["input"])

        data = result.model_dump()
        data["city"] = data["city"] or "Mumbai"

        print("AI Output:", data)

    except Exception as error:
        print("ERROR:", str(error))