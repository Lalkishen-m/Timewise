
# evaluate_timewise.py

import asyncio
import argparse
import math

from dotenv import load_dotenv

load_dotenv(override=True)

from langsmith import Client
from workflow_mcp import app


# =====================================================
# 1. REPEATABLE MUMBAI TEST CASES
# =====================================================

CASES = [
    {
        "name": "Bandra cafe discovery",
        "inputs": {
            "user_request": (
                "Suggest a relaxed cafe to visit "
                "with a friend in Bandra."
            ),
            "search_area": "Bandra",
            "origin_lat": 19.0596,
            "origin_lon": 72.8295,
            "travel_mode": "drive",
            "mode_override": "activities",
            "preference_overrides": {
                "available_minutes": 120,
                "budget_per_person_inr": 500,
                "group_type": "friends",
            },
        },
        "outputs": {
            "expected_mode": "activities",
            "required_categories": ["cafe"],
        },
    },
    {
        "name": "Powai outdoor discovery",
        "inputs": {
            "user_request": (
                "I want an outdoor park activity "
                "in Powai, going solo."
            ),
            "search_area": "Powai",
            "origin_lat": 19.1176,
            "origin_lon": 72.9060,
            "travel_mode": "walk",
            "mode_override": "activities",
            "preference_overrides": {
                "available_minutes": 180,
                "budget_per_person_inr": 300,
                "group_type": "solo",
            },
        },
        "outputs": {
            "expected_mode": "activities",
            "required_categories": ["park"],
        },
    },
    {
        "name": "Bandra cafe and park plan",
        "inputs": {
            "user_request": (
                "Plan an outing with a cafe "
                "and a park in Bandra."
            ),
            "search_area": "Bandra",
            "origin_lat": 19.0596,
            "origin_lon": 72.8295,
            "travel_mode": "drive",
            "mode_override": "plans",
            "preference_overrides": {
                "available_minutes": 240,
                "budget_per_person_inr": 1000,
                "group_type": "friends",
            },
        },
        "outputs": {
            "expected_mode": "plans",
            "required_categories": [
                "cafe", "park"
            ],
        },
    },
    {
        "name": "Colaba food and park plan",
        "inputs": {
            "user_request": (
                "Plan food at a restaurant "
                "and a park visit in Colaba."
            ),
            "search_area": "Colaba",
            "origin_lat": 18.9067,
            "origin_lon": 72.8147,
            "travel_mode": "walk",
            "mode_override": "plans",
            "preference_overrides": {
                "available_minutes": 300,
                "budget_per_person_inr": 1500,
                "group_type": "couple",
            },
        },
        "outputs": {
            "expected_mode": "plans",
            "required_categories": [
                "restaurant", "park"
            ],
        },
    },
]


# =====================================================
# 2. CALL THE ACTUAL TIMEWISE WORKFLOW
# =====================================================

def run_timewise(inputs):

    result = asyncio.run(
        app.ainvoke(inputs)
    )

    final = result.get("final_response") or {}

    return {
        "mode": result.get("selected_mode"),
        "recommended": final.get(
            "recommended", []
        ),
        "time_risks": final.get(
            "time_risks", []
        ),
        "excluded": final.get(
            "excluded", []
        ),
        "itineraries": final.get(
            "itineraries", []
        ),
        "errors": result.get("errors", []),
        "evaluated_count": len(
            result.get(
                "validated_recommendations", []
            )
        ),
    }


# =====================================================
# 3. QUALITY EVALUATORS
# =====================================================

def mode_correct(outputs, reference_outputs):

    return {
        "key": "mode_correct",
        "score": int(
            outputs.get("mode")
            == reference_outputs["expected_mode"]
        ),
    }


def category_relevance(outputs, reference_outputs):

    required = set(
        reference_outputs["required_categories"]
    )

    if outputs.get("mode") == "plans":

        # A single itinerary should cover all
        # categories explicitly requested.
        groups = [
            {
                str(stop.get("category", "")).lower()
                for stop in plan.get("stops", [])
            }
            for plan in outputs.get(
                "itineraries", []
            )
        ]

        matched = any(
            required.issubset(group)
            for group in groups
        )

    else:

        categories = {
            str(place.get("category", "")).lower()
            for place in outputs.get(
                "recommended", []
            )
        }

        matched = required.issubset(categories)

    return {
        "key": "category_relevance",
        "score": int(matched),
    }


def constraint_safety(inputs, outputs):

    budget = inputs.get(
        "preference_overrides", {}
    ).get("budget_per_person_inr")

    safe = True

    for place in outputs.get(
        "recommended", []
    ):

        if (
            place.get("feasibility_status")
            == "not_feasible"
        ):
            safe = False

        if place.get("violations"):
            safe = False

        if place.get("time_assessment") in (
            "estimated_over_budget",
            "over_budget",
        ):
            safe = False

    for plan in outputs.get(
        "itineraries", []
    ):

        total = plan.get("total_minutes")
        available = plan.get(
            "available_minutes"
        )

        if (
            plan.get("status") == "estimated_fit"
            and isinstance(total, (int, float))
            and isinstance(available, (int, float))
            and total > available
        ):
            safe = False

        legs = plan.get(
            "legs_minutes", {}
        )

        if plan.get("status") == "estimated_fit":

            if any(
                not isinstance(v, (int, float))
                or v <= 0
                for v in legs.values()
            ):
                safe = False

        if (
            budget is not None
            and plan.get("total_cost_verified")
            and plan.get(
                "known_cost_per_person_inr", 0
            ) > budget
        ):
            safe = False

    return {
        "key": "constraint_safety",
        "score": int(safe),
    }


def plan_generated(outputs, reference_outputs):

    if reference_outputs["expected_mode"] != "plans":
        return {
            "key": "plan_generated",
            "score": None,
            "comment": "Not applicable to Activities",
        }

    plans = outputs.get("itineraries", [])

    return {
        "key": "plan_generated",
        "score": int(
            any(
                len(plan.get("stops", [])) == 2
                for plan in plans
            )
        ),
    }


def itinerary_arithmetic(outputs, reference_outputs):

    if reference_outputs["expected_mode"] != "plans":
        return {
            "key": "itinerary_arithmetic",
            "score": None,
            "comment": "Not applicable to Activities",
        }

    plans = outputs.get("itineraries", [])

    if not plans:
        return {
            "key": "itinerary_arithmetic",
            "score": 0,
            "comment": "No plan to evaluate",
        }

    valid = True

    for plan in plans:

        stops = plan.get("stops", [])
        legs = plan.get("legs_minutes", {})

        if len(stops) != 2:
            valid = False
            continue

        try:
            calculated = (
                stops[0]["duration_minutes"]
                + stops[1]["duration_minutes"]
                + legs["start_to_first"]
                + legs["first_to_second"]
                + legs["second_to_start"]
                + plan["buffer_minutes"]
            )

            if not math.isclose(
                calculated,
                plan["total_minutes"],
                abs_tol=0.11
            ):
                valid = False

        except (KeyError, TypeError):
            valid = False

    return {
        "key": "itinerary_arithmetic",
        "score": int(valid),
    }


# =====================================================
# 4. CREATE OR REUSE LANGSMITH DATASET
# =====================================================

def get_dataset(client, smoke):

    name = (
        "TimeWise-Mumbai-Smoke-v1"
        if smoke
        else "TimeWise-Mumbai-Quality-v1"
    )

    datasets = list(
        client.list_datasets(
            dataset_name=name
        )
    )

    if datasets:
        return datasets[0]

    dataset = client.create_dataset(
        dataset_name=name,
        description=(
            "TimeWise Mumbai MVP quality tests "
            "for activities and two-stop plans."
        ),
    )

    cases = (
        CASES[:2]
        if smoke
        else CASES
    )

    client.create_examples(
        dataset_id=dataset.id,
        examples=[
            {
                "inputs": case["inputs"],
                "outputs": case["outputs"],
                "metadata": {
                    "test_name": case["name"]
                },
            }
            for case in cases
        ],
    )

    return dataset


# =====================================================
# 5. RUN LANGSMITH EXPERIMENT
# =====================================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run two cheaper activity tests first",
    )

    args = parser.parse_args()

    client = Client()

    dataset = get_dataset(
        client,
        smoke=args.smoke
    )

    print(
        "\nRunning TimeWise quality evaluation..."
    )

    print(
        "Dataset:", dataset.name
    )

    print(
        "This uses live Gemini and Geoapify calls."
    )

    results = client.evaluate(
        run_timewise,
        data=dataset.name,
        evaluators=[
            mode_correct,
            category_relevance,
            constraint_safety,
            plan_generated,
            itinerary_arithmetic,
        ],
        experiment_prefix="timewise-step-5-17",
        description=(
            "Baseline evaluation of Mumbai "
            "recommendation and itinerary quality."
        ),
        max_concurrency=1,
        metadata={
            "version": "step-5.17-baseline",
            "city": "Mumbai",
            "model": "gemini-2.5-flash",
        },
    )

    print(
        "\nEvaluation completed."
    )

    print(
        "Experiment:",
        results.experiment_name
    )

    print(
        "\nOpen LangSmith > Datasets & Experiments "
        "to inspect individual results."
    )


if __name__ == "__main__":
    main()
