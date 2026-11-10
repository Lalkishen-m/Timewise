
# itinerary.py
#
# TimeWise - Category-aware two-stop itinerary planner

from itertools import combinations
import math

from mcp import Client
from mcp_server import mcp


BUFFER_MINUTES = 15
MAX_CANDIDATES = 6
MAX_PAIRS = 8
MAX_PLANS = 3


def is_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def normalized_category(place):
    raw = str(
        place.get("category") or ""
    ).lower()

    if "cafe" in raw or "café" in raw:
        return "cafe"

    if "restaurant" in raw:
        return "restaurant"

    if "park" in raw or "garden" in raw:
        return "park"

    if "cinema" in raw or "movie" in raw:
        return "cinema"

    if "museum" in raw:
        return "museum"

    if "attraction" in raw:
        return "attraction"

    return raw


def venue_key(place):
    return place.get("place_id") or (
        str(place.get("name", "")).casefold(),
        place.get("latitude"),
        place.get("longitude"),
    )


def plan_priority(plan):
    priorities = {
        "estimated_fit": 0,
        "route_needs_verification": 1,
        "time_risk": 2,
    }

    return (
        priorities.get(plan["status"], 3),
        plan["total_minutes"],
        -plan["score"],
    )


async def route_between(
    client,
    first,
    second,
    travel_mode,
):
    try:
        response = await client.call_tool(
            "get_travel_estimate",
            {
                "origin_lat": first["latitude"],
                "origin_lon": first["longitude"],
                "destination_lat": second["latitude"],
                "destination_lon": second["longitude"],
                "mode": travel_mode,
            },
        )

        data = response.structured_content or {}

        if response.is_error or data.get("error"):
            return None

        travel_minutes = data.get("travel_minutes")

        if not is_number(travel_minutes):
            return None

        if travel_minutes < 0:
            return None

        return {
            "minutes": travel_minutes,
            "distance_km": data.get("distance_km"),
        }

    except Exception:
        return None


def create_plan(
    first,
    second,
    between,
    available_minutes,
    budget_per_person,
):
    outward = first["travel_minutes"]
    returning = second["return_travel_minutes"]

    duration_1 = first["duration_minutes"]
    duration_2 = second["duration_minutes"]

    travel_between = between["minutes"]

    total = round(
        outward
        + duration_1
        + travel_between
        + duration_2
        + returning
        + BUFFER_MINUTES,
        2,
    )

    # Known venue prices only
    prices = [
        first.get("price_inr"),
        second.get("price_inr"),
    ]

    known_prices = [
        float(price)
        for price in prices
        if is_number(price) and price >= 0
    ]

    known_cost = round(
        sum(known_prices), 2
    )

    all_prices_known = (
        len(known_prices) == 2
    )

    # Reject a pair when known costs alone
    # exceed the user's per-person budget.
    if (
        is_number(budget_per_person)
        and known_cost > budget_per_person
    ):
        return None

    # Preserve zero-minute route uncertainty
    suspicious_route = any(
        minutes <= 0
        for minutes in (
            outward,
            travel_between,
            returning,
        )
    )

    over_time = (
        is_number(available_minutes)
        and total > available_minutes
    )

    if suspicious_route:
        status = "route_needs_verification"

    elif over_time:
        status = "time_risk"

    else:
        status = "estimated_fit"

    notes = [
        "Opening hours and availability not verified",
        "Travel times are routing estimates",
        "Activity durations may be category estimates",
    ]

    if not all_prices_known:
        notes.append(
            "Complete per-person cost is unknown"
        )

    if suspicious_route:
        notes.append(
            "A zero-minute travel leg needs verification"
        )

    if over_time:
        notes.append(
            "Estimated outing exceeds the time budget"
        )

    score = round(
        (
            float(
                first.get("recommendation_score", 0)
            )
            + float(
                second.get("recommendation_score", 0)
            )
        ) / 2,
        1,
    )

    return {
        "title": (
            f"{first['name']} + {second['name']}"
        ),
        "stops": [first, second],
        "legs_minutes": {
            "start_to_first": outward,
            "first_to_second": travel_between,
            "second_to_start": returning,
        },
        "between_distance_km": (
            between.get("distance_km")
        ),
        "buffer_minutes": BUFFER_MINUTES,
        "total_minutes": total,
        "available_minutes": available_minutes,
        "remaining_minutes": (
            round(available_minutes - total, 2)
            if is_number(available_minutes)
            else None
        ),
        "known_cost_per_person_inr": known_cost,
        "total_cost_verified": all_prices_known,
        "status": status,
        "score": score,
        "notes": notes,
    }


async def build_itineraries(
    places,
    available_minutes,
    budget_per_person,
    travel_mode="drive",
    required_categories=None,
):
    """
    Build up to three two-stop itineraries.

    - Honors explicitly requested categories
    - Evaluates both venue orders
    - Uses MCP for inter-stop routes
    - Does not invent prices or travel times
    """

    required = set(
        required_categories or []
    )

    warnings = []
    candidates = []
    seen = set()

    if len(required) > 2:
        return [], [
            "The current two-stop planner cannot "
            "cover more than two requested categories."
        ]

    # ---------------------------------------------
    # 1. COLLECT ELIGIBLE VENUES
    # ---------------------------------------------

    for place in places:

        key = venue_key(place)

        if key in seen:
            continue

        seen.add(key)

        if place.get(
            "feasibility_status"
        ) == "not_feasible":
            continue

        required_fields = [
            "latitude",
            "longitude",
            "travel_minutes",
            "return_travel_minutes",
            "duration_minutes",
        ]

        if any(
            not is_number(place.get(field))
            for field in required_fields
        ):
            continue

        if any(
            place[field] < 0
            for field in (
                "travel_minutes",
                "return_travel_minutes",
                "duration_minutes",
            )
        ):
            continue

        candidates.append(place)

        if len(candidates) >= MAX_CANDIDATES:
            break

    if len(candidates) < 2:
        return [], [
            "Fewer than two venues have sufficient "
            "routing and duration information."
        ]

    # ---------------------------------------------
    # 2. BUILD CATEGORY-COMPATIBLE PAIRS
    # ---------------------------------------------

    pairs = []

    for first, second in combinations(
        candidates, 2
    ):

        categories = {
            normalized_category(first),
            normalized_category(second),
        }

        # Both explicitly requested activity
        # types must occur in the same plan.
        if not required.issubset(categories):
            continue

        pairs.append((first, second))

    if not pairs:
        return [], [
            "No two-venue combination covers "
            "all requested activity categories."
        ]

    # Prefer category diversity, then venue score.
    pairs.sort(
        key=lambda pair: (
            normalized_category(pair[0])
            == normalized_category(pair[1]),
            -sum(
                float(
                    p.get("recommendation_score", 0)
                )
                for p in pair
            ),
        )
    )

    # ---------------------------------------------
    # 3. COMPARE BOTH VISIT ORDERS
    # ---------------------------------------------

    plans = []

    async with Client(mcp) as client:

        for a, b in pairs[:MAX_PAIRS]:

            alternatives = []

            for first, second in (
                (a, b),
                (b, a),
            ):

                between = await route_between(
                    client,
                    first,
                    second,
                    travel_mode,
                )

                if between is None:
                    continue

                plan = create_plan(
                    first=first,
                    second=second,
                    between=between,
                    available_minutes=available_minutes,
                    budget_per_person=budget_per_person,
                )

                if plan is not None:
                    alternatives.append(plan)

            if alternatives:

                # For this venue pair, choose the
                # better of the two possible orders.
                alternatives.sort(
                    key=plan_priority
                )

                plans.append(
                    alternatives[0]
                )

    # ---------------------------------------------
    # 4. SELECT THE BEST PLANS
    # ---------------------------------------------

    plans.sort(
        key=plan_priority
    )

    selected = plans[:MAX_PLANS]

    if not selected:
        warnings.append(
            "No routable, budget-compatible "
            "two-stop itinerary was constructed."
        )

    if selected and not any(
        p["status"] == "estimated_fit"
        for p in selected
    ):
        warnings.append(
            "No itinerary currently has a "
            "fully positive route estimate "
            "within the time budget."
        )

    return selected, warnings
