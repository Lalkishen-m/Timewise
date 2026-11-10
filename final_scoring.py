
# final_scoring.py
#
# Deterministic recommendation scoring for TimeWise.
# Uses only data already retrieved or calculated.
# Does not call Gemini or any external API.


def is_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
    )


def score_place(place, rank_index, budget):
    """
    Score a previously ranked and validated venue.

    Maximum: 100 points.

    Relevance: 40
    Time fit: 25
    Travel convenience: 20
    Known budget fit: 10
    Location coordinates: 5
    """

    item = place.copy()
    breakdown = {}

    # 1. RELEVANCE
    # Earlier places in the AI-ranked list
    # receive higher relevance scores.
    breakdown["relevance"] = max(
        0, 40 - (rank_index * 5)
    )

    # 2. TIME FIT
    time_assessment = item.get("time_assessment")

    outward = item.get("travel_minutes")
    return_time = item.get("return_travel_minutes")

    # A zero-minute route is suspicious until verified.
    suspicious_route = (
        (is_number(outward) and outward <= 0)
        or
        (is_number(return_time) and return_time <= 0)
    )

    if (
        time_assessment == "estimated_fit"
        and not suspicious_route
    ):
        breakdown["time_fit"] = 25
    else:
        breakdown["time_fit"] = 0

    # 3. TRAVEL CONVENIENCE
    round_trip = item.get(
        "round_trip_travel_minutes"
    )

    if (
        is_number(round_trip)
        and round_trip > 0
        and not suspicious_route
    ):
        breakdown["travel"] = max(
            0,
            round(20 - round_trip / 6, 1)
        )
    else:
        breakdown["travel"] = 0

    # 4. KNOWN BUDGET FIT
    price = item.get("price_inr")

    if (
        is_number(budget)
        and is_number(price)
        and price >= 0
        and price <= budget
    ):
        breakdown["budget"] = 10
    else:
        breakdown["budget"] = 0

    # 5. LOCATION DATA
    has_coordinates = (
        is_number(item.get("latitude"))
        and is_number(item.get("longitude"))
    )

    breakdown["location"] = (
        5 if has_coordinates else 0
    )

    item["recommendation_score"] = round(
        sum(breakdown.values()), 1
    )

    item["score_breakdown"] = breakdown

    # Build transparent, factual explanations.
    notes = []

    if item.get("duration_is_estimated"):
        notes.append(
            "Activity duration is a planning estimate"
        )

    if is_number(budget) and not is_number(price):
        notes.append("Price not verified")

    if suspicious_route:
        notes.append(
            "Zero-minute route needs verification"
        )

    if outward is None or return_time is None:
        notes.append(
            "Round-trip travel is incomplete"
        )

    notes.append(
        "Opening hours not verified"
    )

    item["recommendation_notes"] = notes

    return item


def build_final_response(state):
    """
    Convert validated recommendations into
    a scored, explainable customer-facing result.
    """

    preferences = state.get("preferences", {})

    budget = preferences.get(
        "budget_per_person_inr"
    )

    places = state.get(
        "validated_recommendations", []
    )

    recommended = []
    time_risks = []
    excluded = []

    for index, place in enumerate(places):

        item = score_place(
            place=place,
            rank_index=index,
            budget=budget
        )

        feasibility = item.get(
            "feasibility_status"
        )

        time_assessment = item.get(
            "time_assessment"
        )

        # Known constraint violation:
        # do not recommend as a feasible option.
        if feasibility == "not_feasible":
            excluded.append(item)

        # Estimated overrun:
        # show separately instead of recommending.
        elif time_assessment in (
            "estimated_over_budget",
            "over_budget"
        ):
            time_risks.append(item)

        else:
            recommended.append(item)

    # Highest-scoring eligible venues first
    recommended.sort(
        key=lambda x: x["recommendation_score"],
        reverse=True
    )

    time_risks.sort(
        key=lambda x: x["recommendation_score"],
        reverse=True
    )

    # MVP: display up to five primary suggestions
    recommended = recommended[:5]

    if recommended:
        summary = (
            f"Found {len(recommended)} candidate "
            "activities ranked by relevance and "
            "planning feasibility. Verify prices, "
            "opening hours and travel estimates."
        )

    elif time_risks:
        summary = (
            "No shortlisted activity currently "
            "fits the estimated time budget. "
            "Some options may work with a "
            "shorter visit or different travel plan."
        )

    else:
        summary = (
            "No suitable recommendations remain "
            "after checking available constraints. "
            "Try changing the location, budget "
            "or available time."
        )

    return {
        "mode": state.get(
            "selected_mode", "activities"
        ),
        "summary": summary,
        "recommended": recommended,
        "time_risks": time_risks,
        "excluded": excluded,
        "total_evaluated": len(places),
        "disclaimer": (
            "Scores are planning heuristics, "
            "not venue ratings. Unknown prices, "
            "opening hours and availability "
            "have not been verified."
        )
    }
