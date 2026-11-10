
# diagnose_plans.py
# Inspect existing TimeWise LangSmith experiment.
# No Gemini or Geoapify calls.

from dotenv import load_dotenv
from langsmith import Client

from analyze_baseline import (
    get_experiment,
    DATASET,
    plan_is_usable,
)

load_dotenv(override=True)

client = Client()
experiment = get_experiment(client)

examples = {
    str(example.id): example
    for example in client.list_examples(
        dataset_name=DATASET
    )
}

runs = client.list_runs(
    project_id=str(experiment.id),
    is_root=True,
)

print("\n=== TIMEWISE PLAN DIAGNOSIS ===")
print("Experiment:", experiment.name)

for run in runs:

    example = examples.get(
        str(run.reference_example_id)
    )

    if example is None:
        continue

    reference = example.outputs or {}

    if reference.get("expected_mode") != "plans":
        continue

    name = (example.metadata or {}).get(
        "test_name", "Unnamed test"
    )

    required = reference.get(
        "required_categories", []
    )

    plans = (
        (run.outputs or {}).get("itineraries")
        or []
    )

    print("\n" + "=" * 45)
    print("TEST:", name)
    print("Required categories:", required)
    print("Plans returned:", len(plans))

    if not plans:
        print("ISSUE: No itinerary generated.")
        continue

    for index, plan in enumerate(plans, 1):

        print(f"\nPlan {index}: {plan.get('title')}")

        stops = plan.get("stops") or []

        categories = [
            stop.get("category")
            for stop in stops
        ]

        print("Categories:", categories)
        print("Status:", plan.get("status"))

        print(
            "Total time:",
            plan.get("total_minutes")
        )

        print(
            "Available time:",
            plan.get("available_minutes")
        )

        print(
            "Time remaining:",
            plan.get("remaining_minutes")
        )

        print(
            "Travel legs:",
            plan.get("legs_minutes")
        )

        print(
            "All costs verified:",
            plan.get("total_cost_verified")
        )

        usable = plan_is_usable(
            plan,
            required
        )

        print(
            "Provisionally usable:",
            "YES" if usable else "NO"
        )

        if not usable:

            legs = plan.get(
                "legs_minutes") or {}

            if plan.get("status") == "time_risk":
                print(
                    "Reason: Estimated time exceeded."
                )

            if any(
                not isinstance(v, (int, float))
                or v <= 0
                for v in legs.values()
            ):
                print(
                    "Reason: Missing or zero-minute "
                    "travel leg."
                )

            if plan.get("status") == "route_needs_verification":
                print(
                    "Reason: Routing needs verification."
                )

            print(
                "Check whether both requested "
                "categories occur in this plan."
            )
