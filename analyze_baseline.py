
# analyze_baseline.py
#
# TimeWise Step 5.18
# Read existing LangSmith results and local feedback.
# No Gemini or Geoapify calls.

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

from langsmith import Client


DATASET = "TimeWise-Mumbai-Quality-v1"
EXPERIMENT_PREFIX = "timewise-step-5-17"

METRICS = [
    "mode_correct",
    "category_relevance",
    "constraint_safety",
    "plan_generated",
    "itinerary_arithmetic",
]

TARGETS = {
    "mode_correct": 1.0,
    "category_relevance": 0.80,
    "constraint_safety": 1.0,
    "plan_generated": 0.70,
    "itinerary_arithmetic": 1.0,
}


def numeric(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
    )


def score_value(value):
    if isinstance(value, bool):
        return float(value)

    if numeric(value):
        return float(value)

    return None


def percentage(value):
    if value is None:
        return "Not available"

    return f"{value * 100:.1f}%"


def get_experiment(client, selected_name=None):

    if selected_name:
        return client.read_project(
            project_name=selected_name,
            include_stats=True,
        )

    projects = list(
        client.list_projects(
            reference_dataset_name=DATASET
        )
    )

    projects = [
        p for p in projects
        if p.name.startswith(EXPERIMENT_PREFIX)
    ]

    if not projects:
        raise RuntimeError(
            "No matching experiment found. "
            "Copy its exact name from LangSmith "
            "and pass --experiment NAME."
        )

    def sort_key(project):
        date = (
            getattr(project, "start_time", None)
            or getattr(project, "created_at", None)
        )
        return date.isoformat() if date else ""

    latest = max(projects, key=sort_key)

    return client.read_project(
        project_id=str(latest.id),
        include_stats=True,
    )


def matches_category(actual, expected):
    actual = str(actual or "").lower()
    expected = str(expected).lower()

    return (
        actual == expected
        or actual.endswith("." + expected)
    )


def plan_is_usable(plan, required_categories):

    if plan.get("status") != "estimated_fit":
        return False

    stops = plan.get("stops") or []

    if len(stops) != 2:
        return False

    legs = (
        plan.get("legs_minutes") or {}
    )

    # Reject zero or missing route legs.
    if any(
        not numeric(value) or value <= 0
        for value in [
            legs.get("start_to_first"),
            legs.get("first_to_second"),
            legs.get("second_to_start"),
        ]
    ):
        return False

    total = plan.get("total_minutes")
    available = plan.get("available_minutes")

    if (
        not numeric(total)
        or not numeric(available)
        or total > available
    ):
        return False

    # Every requested category must appear
    # within this SAME itinerary.
    for category in required_categories:

        if not any(
            matches_category(
                stop.get("category"),
                category
            )
            for stop in stops
        ):
            return False

    # This is still provisionally usable:
    # prices and opening hours may be unknown.
    return True


def read_local_feedback():

    path = (
        Path(__file__).resolve().parent
        / "timewise_feedback.jsonl"
    )

    if not path.exists():
        return []

    records = []

    with path.open(
        encoding="utf-8"
    ) as file:

        for line in file:
            try:
                record = json.loads(line)

                if isinstance(record, dict):
                    records.append(record)

            except json.JSONDecodeError:
                continue

    return records


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--experiment",
        default=None,
        help="Exact LangSmith experiment name",
    )

    args = parser.parse_args()

    client = Client()

    experiment = get_experiment(
        client,
        selected_name=args.experiment,
    )

    print("\n=== TIMEWISE BASELINE REPORT ===")
    print("Experiment:", experiment.name)
    print("Dataset:", DATASET)

    # -----------------------------------------
    # A. Fetch test examples and experiment runs
    # -----------------------------------------

    examples = {
        str(example.id): example
        for example in client.list_examples(
            dataset_name=DATASET
        )
    }

    runs = list(
        client.list_runs(
            project_id=str(experiment.id),
            is_root=True,
        )
    )

    print("Test executions:", len(runs))

    if not runs:
        print("No completed run data found.")
        return

    # -----------------------------------------
    # B. Fetch evaluator scores by run
    # -----------------------------------------

    feedback = list(
        client.list_feedback(
            run_ids=[
                str(run.id)
                for run in runs
            ]
        )
    )

    by_run = defaultdict(dict)

    for entry in feedback:

        if entry.key not in METRICS:
            continue

        value = score_value(entry.score)

        if value is not None:
            by_run[str(entry.run_id)][
                entry.key
            ] = value

    # -----------------------------------------
    # C. Aggregate baseline metrics
    # -----------------------------------------

    aggregates = defaultdict(list)
    failures = []
    plan_count = 0
    usable_plan_count = 0
    errored_runs = 0

    for run in runs:

        run_id = str(run.id)

        example = examples.get(
            str(run.reference_example_id)
        )

        metadata = (
            example.metadata or {}
            if example else {}
        )

        test_name = metadata.get(
            "test_name",
            str(run.reference_example_id)[:8]
        )

        references = (
            example.outputs or {}
            if example else {}
        )

        output = run.outputs or {}

        if run.error:
            errored_runs += 1

        for metric in METRICS:

            value = by_run[run_id].get(metric)

            if value is None:
                continue

            aggregates[metric].append(value)

            if value == 0:
                failures.append(
                    (test_name, metric)
                )

        # Additional quality check:
        # Is a plan actually time-fitting,
        # routable, and category-complete?
        if references.get(
            "expected_mode"
        ) == "plans":

            plan_count += 1

            plans = (
                output.get("itineraries") or []
            )

            required = references.get(
                "required_categories", []
            )

            if any(
                plan_is_usable(
                    plan,
                    required
                )
                for plan in plans
            ):
                usable_plan_count += 1

    print("\n--- EVALUATOR RESULTS ---")

    averages = {}

    for metric in METRICS:

        values = aggregates.get(
            metric, []
        )

        average = (
            sum(values) / len(values)
            if values else None
        )

        averages[metric] = average

        print(
            f"{metric}: "
            f"{percentage(average)} "
            f"({len(values)} scored runs)"
        )

    usable_rate = (
        usable_plan_count / plan_count
        if plan_count else None
    )

    print(
        "\nProvisionally usable "
        "category-complete plans:",
        percentage(usable_rate),
        f"({usable_plan_count}/{plan_count})"
    )

    print(
        "Runs with execution errors:",
        errored_runs
    )

    print("\n--- FAILED CHECKS ---")

    if not failures:
        print(
            "No recorded zero-score checks. "
            "Check for missing evaluator scores."
        )

    for name, metric in failures:
        print(f"- {name}: {metric}")

    missing = []

    for metric in METRICS:
        expected_count = (
            plan_count
            if metric in (
                "plan_generated",
                "itinerary_arithmetic"
            )
            else len(runs)
        )

        actual_count = len(
            aggregates.get(metric, [])
        )

        if actual_count < expected_count:
            missing.append(
                f"{metric}: {actual_count}/"
                f"{expected_count} scores available"
            )

    if missing:
        print("\n--- MISSING EVALUATIONS ---")

        for message in missing:
            print("-", message)

    # -----------------------------------------
    # D. User feedback summary
    # -----------------------------------------

    records = read_local_feedback()

    ratings = [
        r["rating"]
        for r in records
        if numeric(r.get("rating"))
        and 1 <= r["rating"] <= 5
    ]

    issues = Counter(
        r.get("issue")
        for r in records
        if r.get("issue")
        and r.get("issue") != "Nothing specific"
    )

    print("\n--- USER FEEDBACK ---")
    print("Ratings received:", len(ratings))

    if ratings:
        average_rating = (
            sum(ratings) / len(ratings)
        )

        print(
            "Average usefulness:",
            f"{average_rating:.2f}/5"
        )

    else:
        print("Average usefulness: No data")

    print("Reported issues:")

    if issues:
        for issue, count in issues.most_common():
            print(f"- {issue}: {count}")
    else:
        print("- None recorded")

    # -----------------------------------------
    # E. Data-driven priorities
    # -----------------------------------------

    print("\n--- IMPROVEMENT PRIORITIES ---")

    p0 = []

    if errored_runs:
        p0.append(
            "Investigate workflow execution errors"
        )

    if (
        averages["constraint_safety"]
        is not None
        and averages["constraint_safety"] < 1
    ):
        p0.append(
            "Fix known constraint-safety failures"
        )

    if (
        averages["itinerary_arithmetic"]
        is not None
        and averages["itinerary_arithmetic"] < 1
    ):
        p0.append(
            "Fix itinerary duration arithmetic"
        )

    p1 = []

    if (
        averages["category_relevance"]
        is not None
        and averages["category_relevance"] < 0.80
    ):
        p1.append(
            "Improve requested-category coverage"
        )

    if (
        usable_rate is not None
        and usable_rate < 0.70
    ):
        p1.append(
            "Improve time-fitting, category-complete "
            "two-stop itineraries"
        )

    if p0:
        print("P0 — Release blockers")
        for item in p0:
            print("-", item)
    else:
        print(
            "P0 — No failures detected by "
            "available checks; not a safety guarantee"
        )

    if p1:
        print("\nP1 — Recommendation quality")
        for item in p1:
            print("-", item)
    else:
        print(
            "\nP1 — No threshold breaches "
            "in available scored tests"
        )

    if issues:
        print(
            "\nUser-reported improvement area:",
            issues.most_common(1)[0][0]
        )

    print(
        "\nReminder: Four test cases are "
        "insufficient for a deployment decision."
    )


if __name__ == "__main__":
    main()
