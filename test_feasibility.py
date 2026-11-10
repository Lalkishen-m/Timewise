
from feasibility import validate_places

preferences = {
    "budget_per_person_inr": 500,
    "available_minutes": 120
}

places = [
    {
        "name": "Test Cafe A",
        "price_inr": 300,
        "duration_minutes": 90,
        "latitude": 19.0596,
        "longitude": 72.8295
    },
    {
        "name": "Test Cafe B",
        "price_inr": 800,
        "duration_minutes": 60,
        "latitude": 19.0596,
        "longitude": 72.8295
    },
    {
        "name": "Test Cafe C",
        "price_inr": None,
        "duration_minutes": None,
        "latitude": 19.0596,
        "longitude": 72.8295
    }
]

results = validate_places(
    "Suggest cafes in Bandra",
    preferences,
    places
)

for item in results:
    print(
        item["name"],
        "=>",
        item["feasibility_status"]
    )
    print("Violations:", item["violations"])
    print("Unknowns:", item["unknowns"])
    print()
