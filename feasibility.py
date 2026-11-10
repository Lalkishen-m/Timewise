
"""Deterministic feasibility checks for TimeWise."""

import math
from typing import Any


DURATION_ESTIMATES = {
    "cafe": 60,
    "restaurant": 75,
    "park": 60,
    "cinema": 150,
    "museum": 90,
    "attraction": 90,
}


def _number(value: Any) -> bool:

    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def estimate_activity_duration(
    place: dict[str, Any]
) -> int:

    """
    Use an explicit duration if available.
    Otherwise use category-based estimates.
    """

    existing = place.get("duration_minutes")

    if _number(existing) and existing > 0:
        return int(existing)

    category = (
        str(place.get("category") or "")
        .lower()
        .replace("é", "e")
    )

    for name, minutes in (
        DURATION_ESTIMATES.items()
    ):

        if (
            name in category
            or (
                name == "park"
                and "garden" in category
            )
        ):
            return minutes

    return 90


def validate_places(
    request: str,
    preferences: dict[str, Any],
    places: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    """
    Validate known constraints.

    Missing costs and route estimates must
    remain unknown, not become zero.
    """

    available = preferences.get(
        "available_minutes"
    )

    budget = preferences.get(
        "budget_per_person_inr"
    )

    # Origin-based radius; Activities only.
    radius_km = preferences.get(
        "search_radius_km"
    )

    validated = []

    for original in places:

        item = dict(original)

        violations: list[str] = []
        unknowns: list[str] = []

        duration_was_explicit = (
            _number(
                item.get("duration_minutes")
            )
            and item["duration_minutes"] > 0
        )

        duration = estimate_activity_duration(
            item
        )

        item["duration_minutes"] = duration

        item["duration_is_estimated"] = (
            not duration_was_explicit
        )

        item["duration_source"] = (
            "Venue-supplied"
            if duration_was_explicit
            else "Category-based planning estimate"
        )

        # -------------------------------------
        # BUDGET VALIDATION
        # -------------------------------------

        price = item.get("price_inr")

        if not _number(price):
            unknowns.append(
                "Price not verified"
            )

        elif (
            _number(budget)
            and price > budget
        ):
            violations.append(
                "Known price exceeds per-person budget"
            )

        # -------------------------------------
        # OPENING HOURS
        # -------------------------------------

        if not item.get(
            "opening_hours_verified",
            False
        ):
            unknowns.append(
                "Opening hours not verified"
            )

        # -------------------------------------
        # LOCATION VALIDATION
        # -------------------------------------

        straight_line = item.get(
            "straight_line_km"
        )

        if (
            _number(radius_km)
            and _number(straight_line)
            and straight_line > radius_km + 0.05
        ):
            violations.append(
                "Outside requested discovery radius"
            )

        # -------------------------------------
        # ROUND-TRIP TRAVEL VALIDATION
        # -------------------------------------

        outbound = item.get(
            "travel_minutes"
        )

        returning = item.get(
            "return_travel_minutes"
        )

        if (
            _number(outbound)
            and _number(returning)
            and outbound >= 0
            and returning >= 0
        ):

            round_trip = round(
                outbound + returning,
                2
            )

            item[
                "round_trip_travel_minutes"
            ] = round_trip

            total = round(
                round_trip + duration,
                2
            )

            item[
                "estimated_total_minutes"
            ] = total

            item[
                "total_outing_minutes"
            ] = total

            if (
                outbound <= 0
                or returning <= 0
            ):

                item["time_assessment"] = (
                    "route_needs_verification"
                )

                unknowns.append(
                    "Zero-minute route leg needs verification"
                )

            elif _number(available):

                item["time_assessment"] = (
                    "estimated_fit"
                    if total <= available
                    else "estimated_over_budget"
                )

            else:

                item["time_assessment"] = (
                    "unknown"
                )

                unknowns.append(
                    "Available time not provided"
                )

        else:

            item["time_assessment"] = (
                "unknown"
            )

            item[
                "estimated_total_minutes"
            ] = None

            item[
                "total_outing_minutes"
            ] = None

            unknowns.append(
                "Travel route not available"
            )

        # -------------------------------------
        # FINAL FEASIBILITY STATUS
        # -------------------------------------

        if violations:

            item["feasibility_status"] = (
                "not_feasible"
            )

        elif unknowns:

            item["feasibility_status"] = (
                "needs_verification"
            )

        else:

            item["feasibility_status"] = (
                "passes_known_constraints"
            )

        item["violations"] = violations

        item["unknowns"] = unknowns

        item["feasibility_notes"] = (
            violations + unknowns
        )

        validated.append(item)

    return validated
