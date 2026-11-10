
"""TimeWise LangGraph: dynamic Activities discovery, existing Plans workflow."""

import asyncio
import logging
import re
from typing import Any, TypedDict

from dotenv import load_dotenv

load_dotenv(override=True)

logging.getLogger("httpx").setLevel(
    logging.WARNING
)

from langgraph.graph import (
    StateGraph,
    START,
    END
)

from langsmith import traceable
from mcp import Client

from mcp_server import mcp

from intent_extractor import extract_preferences
from ranking import rank_places
from feasibility import validate_places

from final_scoring import (
    build_final_response,
    score_place
)

from itinerary import build_itineraries


# =============================================
# CONFIGURATION
# =============================================

AREAS = [
    "Bandra",
    "Andheri",
    "Dadar",
    "Colaba",
    "Powai"
]

KEYWORDS = {
    "cafe": [
        "cafe",
        "cafes",
        "café",
        "cafés",
        "coffee"
    ],

    "restaurant": [
        "restaurant",
        "restaurants",
        "food",
        "dining",
        "dinner",
        "lunch",
        "breakfast"
    ],

    "park": [
        "park",
        "parks",
        "garden",
        "gardens",
        "outdoor",
        "outdoors"
    ],

    "cinema": [
        "cinema",
        "cinemas",
        "movie",
        "movies",
        "film"
    ],

    "museum": [
        "museum",
        "museums"
    ],

    "attraction": [
        "attraction",
        "sightseeing"
    ]
}


# =============================================
# LANGGRAPH STATE
# =============================================

class TimeWiseState(TypedDict, total=False):

    user_request: str

    preference_overrides: dict[str, Any]

    mode_override: str | None

    search_area: str

    origin_lat: float
    origin_lon: float

    travel_mode: str

    search_radius_m: int

    preferences: dict[str, Any]

    selected_mode: str

    places: list[dict[str, Any]]

    errors: list[str]

    recommendations: list[dict[str, Any]]

    validated_recommendations: list[
        dict[str, Any]
    ]

    itineraries: list[dict[str, Any]]

    itinerary_warnings: list[str]

    final_response: dict[str, Any]


# =============================================
# CATEGORY DETECTION
# =============================================

def categories_from_text(
    text: str
) -> list[str]:

    return [
        category

        for category, keywords in KEYWORDS.items()

        if any(
            re.search(
                rf"\b{re.escape(word)}\b",
                text,
                re.I
            )

            for word in keywords
        )
    ]


# =============================================
# LEGACY AREA DETECTION
# PLANS ONLY
# =============================================

def get_area(
    state: TimeWiseState
) -> str:

    selected = state.get(
        "search_area"
    )

    if selected in AREAS:
        return selected

    for area in AREAS:

        if re.search(
            rf"\b{re.escape(area)}\b",
            state.get("user_request", ""),
            re.I
        ):
            return area

    return "Bandra"


# =============================================
# INTENT UNDERSTANDING
# =============================================

def understand_intent(
    state: TimeWiseState
) -> dict[str, Any]:

    extracted = extract_preferences(
        state["user_request"]
    )

    if hasattr(extracted, "model_dump"):
        preferences = extracted.model_dump()
    else:
        preferences = dict(extracted)

    preferences["city"] = (
        preferences.get("city")
        or "Mumbai"
    )

    overrides = (
        state.get("preference_overrides")
        or {}
    )

    for key in (
        "available_minutes",
        "budget_per_person_inr",
        "group_type"
    ):

        if key in overrides:
            preferences[key] = overrides[key]

    mode = state.get(
        "mode_override"
    )

    if mode not in ("activities", "plans"):
        mode = preferences.get(
            "recommended_mode",
            "activities"
        )

    if mode not in ("activities", "plans"):
        mode = "activities"

    preferences["recommended_mode"] = mode

    return {
        "preferences": preferences,
        "selected_mode": mode
    }


# =============================================
# LEGACY MCP DISCOVERY
# PLANS ONLY
# =============================================

@traceable(
    name="MCP Place Discovery",
    run_type="tool"
)
async def find_places(
    categories: list[str],
    area: str
):

    places = []
    errors = []

    async with Client(mcp) as client:

        for category in categories:

            try:

                response = await client.call_tool(
                    "search_places",

                    {
                        "category": category,
                        "area": area,
                        "limit": 3
                    }
                )

                data = (
                    response.structured_content
                    or {}
                )

                if (
                    response.is_error
                    or data.get("error")
                ):

                    errors.append(
                        f"{category}: "
                        f"{data.get('error', 'MCP error')}"
                    )

                else:

                    places.extend(
                        p
                        for p in data.get(
                            "places", []
                        )
                        if p.get("name")
                    )

            except Exception as exc:

                errors.append(
                    f"{category}: "
                    f"{type(exc).__name__}"
                )

    return places, errors


# =============================================
# NEW DYNAMIC ACTIVITIES DISCOVERY
# =============================================

async def activity_path(
    state: TimeWiseState
) -> dict[str, Any]:

    """
    Discover Activities near the user's
    actual starting coordinates.
    """

    lat = state.get("origin_lat")
    lon = state.get("origin_lon")

    if lat is None or lon is None:

        return {
            "places": [],
            "errors": [
                "Enter a starting address "
                "to discover nearby activities."
            ]
        }

    interests = (
        state["preferences"].get(
            "interests"
        )
        or []
    )

    query = (
        state["user_request"]
        + " "
        + " ".join(
            map(str, interests)
        )
    )

    categories = (
        categories_from_text(query)
        or [
            "cafe",
            "park",
            "attraction"
        ]
    )

    radius = max(
        500,
        min(
            int(
                state.get("search_radius_m")
                or 6000
            ),
            20000
        )
    )

    places = []
    errors = []
    seen = set()

    async with Client(mcp) as client:

        for category in categories[:3]:

            try:

                response = await client.call_tool(
                    "search_places_near_origin",

                    {
                        "latitude": lat,
                        "longitude": lon,
                        "category": category,
                        "radius_m": radius,
                        "limit": 15
                    }
                )

                data = (
                    response.structured_content
                    or {}
                )

                if (
                    response.is_error
                    or data.get("error")
                ):

                    errors.append(
                        f"{category}: "
                        f"{data.get('error', 'MCP error')}"
                    )

                    continue

                for place in data.get(
                    "places", []
                ):

                    key = (
                        place.get("place_id")
                        or (
                            place.get(
                                "name", ""
                            ).casefold(),

                            place.get(
                                "latitude"
                            ),

                            place.get(
                                "longitude"
                            )
                        )
                    )

                    if (
                        place.get("name")
                        and key not in seen
                    ):

                        seen.add(key)

                        places.append(place)

            except Exception as exc:

                errors.append(
                    f"{category}: "
                    f"{type(exc).__name__}"
                )

    return {
        "places": places,
        "errors": errors
    }


# =============================================
# EXISTING PLANS DISCOVERY
# =============================================

async def plan_path(
    state: TimeWiseState
) -> dict[str, Any]:

    """
    Keep the existing five-area
    Plans discovery for now.
    """

    interests = (
        state["preferences"].get(
            "interests"
        )
        or []
    )

    query = (
        state["user_request"]
        + " "
        + " ".join(
            map(str, interests)
        )
    )

    categories = (
        categories_from_text(query)
        or ["cafe", "park"]
    )

    if len(categories) == 1:

        complement = (
            "park"
            if categories[0] in (
                "cafe",
                "restaurant"
            )
            else "cafe"
        )

        if complement not in categories:
            categories.append(complement)

    places, errors = await find_places(
        categories[:3],
        get_area(state)
    )

    return {
        "places": places,
        "errors": errors
    }


# =============================================
# GEMINI RANKING
# =============================================

async def rank_recommendations(
    state: TimeWiseState
) -> dict[str, Any]:

    if not state.get("places"):

        return {
            "recommendations": []
        }

    ranked = await rank_places(
        request=state["user_request"],

        preferences=state["preferences"],

        places=state.get(
            "places", []
        )
    )

    return {
        "recommendations": ranked
    }


# =============================================
# ROUTING + FEASIBILITY
# =============================================

async def validate_feasibility(
    state: TimeWiseState
) -> dict[str, Any]:

    """
    Calculate outward and return
    road estimates for shortlisted venues.
    """

    places = [
        dict(p)

        for p in state.get(
            "recommendations", []
        )
    ]

    lat = state.get("origin_lat")
    lon = state.get("origin_lon")

    travel_mode = state.get(
        "travel_mode",
        "drive"
    )

    if lat is not None and lon is not None:

        async with Client(mcp) as client:

            for place in places:

                plat = place.get(
                    "latitude"
                )

                plon = place.get(
                    "longitude"
                )

                if plat is None or plon is None:

                    place["travel_error"] = (
                        "Venue coordinates unavailable"
                    )

                    continue

                legs = (
                    (
                        "outward",
                        lat,
                        lon,
                        plat,
                        plon
                    ),

                    (
                        "return",
                        plat,
                        plon,
                        lat,
                        lon
                    )
                )

                for (
                    direction,
                    from_lat,
                    from_lon,
                    to_lat,
                    to_lon
                ) in legs:

                    try:

                        response = (
                            await client.call_tool(
                                "get_travel_estimate",

                                {
                                    "origin_lat": from_lat,
                                    "origin_lon": from_lon,

                                    "destination_lat": to_lat,
                                    "destination_lon": to_lon,

                                    "mode": travel_mode
                                }
                            )
                        )

                        data = (
                            response.structured_content
                            or {}
                        )

                        minutes = data.get(
                            "travel_minutes"
                        )

                        if (
                            response.is_error
                            or data.get("error")
                            or minutes is None
                        ):

                            error_field = (
                                "travel_error"
                                if direction == "outward"
                                else "return_travel_error"
                            )

                            place[error_field] = (
                                data.get("error")
                                or "Routing unavailable"
                            )

                            continue

                        if direction == "outward":

                            place[
                                "travel_minutes"
                            ] = minutes

                            place[
                                "travel_distance_km"
                            ] = data.get(
                                "distance_km"
                            )

                        else:

                            place[
                                "return_travel_minutes"
                            ] = minutes

                            place[
                                "return_distance_km"
                            ] = data.get(
                                "distance_km"
                            )

                        place["travel_mode"] = (
                            travel_mode
                        )

                    except Exception as exc:

                        error_field = (
                            "travel_error"
                            if direction == "outward"
                            else "return_travel_error"
                        )

                        place[error_field] = (
                            type(exc).__name__
                        )

    else:

        for place in places:

            place["travel_error"] = (
                "Starting coordinates not provided"
            )

    validation_preferences = dict(
        state["preferences"]
    )

    # Crucial: radius is origin-based
    # ONLY for Activities.
    # Legacy Plans retain their own
    # discovery filtering.

    if state["selected_mode"] == "activities":

        validation_preferences[
            "search_radius_km"
        ] = (
            state.get(
                "search_radius_m",
                6000
            ) / 1000
        )

    validated = validate_places(
        request=state["user_request"],

        preferences=validation_preferences,

        places=places
    )

    return {
        "validated_recommendations": validated
    }


# =============================================
# EXISTING ITINERARY BUILDER
# =============================================

async def assemble_plans(
    state: TimeWiseState
) -> dict[str, Any]:

    prefs = state["preferences"]

    scored_venues = [
        score_place(
            place,
            i,
            prefs.get(
                "budget_per_person_inr"
            )
        )

        for i, place in enumerate(
            state.get(
                "validated_recommendations",
                []
            )
        )
    ]

    required = categories_from_text(
        state["user_request"]
    )

    plans, warnings = await build_itineraries(
        places=scored_venues,

        available_minutes=prefs.get(
            "available_minutes"
        ),

        budget_per_person=prefs.get(
            "budget_per_person_inr"
        ),

        travel_mode=state.get(
            "travel_mode",
            "drive"
        ),

        required_categories=required
    )

    return {
        "itineraries": plans,
        "itinerary_warnings": warnings
    }


# =============================================
# FINAL RESPONSE
# =============================================

def finalize_recommendations(
    state: TimeWiseState
) -> dict[str, Any]:

    final = build_final_response(
        state
    )

    if state["selected_mode"] == "plans":

        plans = state.get(
            "itineraries", []
        )

        final["itineraries"] = plans

        final["itinerary_warnings"] = (
            state.get(
                "itinerary_warnings",
                []
            )
        )

        if plans:

            final["summary"] = (
                f"Generated {len(plans)} "
                "two-stop itinerary options; "
                "verify prices and hours."
            )

        else:

            final["summary"] = (
                "No category-compatible two-stop "
                "itinerary could be constructed."
            )

    return {
        "final_response": final
    }


# =============================================
# LANGGRAPH WORKFLOW
# =============================================

def choose_mode(
    state: TimeWiseState
) -> str:

    return state["selected_mode"]


builder = StateGraph(
    TimeWiseState
)

builder.add_node(
    "understand_intent",
    understand_intent
)

builder.add_node(
    "activity_path",
    activity_path
)

builder.add_node(
    "plan_path",
    plan_path
)

builder.add_node(
    "rank_recommendations",
    rank_recommendations
)

builder.add_node(
    "validate_feasibility",
    validate_feasibility
)

builder.add_node(
    "assemble_plans",
    assemble_plans
)

builder.add_node(
    "finalize_recommendations",
    finalize_recommendations
)

builder.add_edge(
    START,
    "understand_intent"
)

builder.add_conditional_edges(
    "understand_intent",
    choose_mode,

    {
        "activities": "activity_path",
        "plans": "plan_path"
    }
)

builder.add_edge(
    "activity_path",
    "rank_recommendations"
)

builder.add_edge(
    "plan_path",
    "rank_recommendations"
)

builder.add_edge(
    "rank_recommendations",
    "validate_feasibility"
)

builder.add_conditional_edges(
    "validate_feasibility",
    choose_mode,

    {
        "activities": "finalize_recommendations",
        "plans": "assemble_plans"
    }
)

builder.add_edge(
    "assemble_plans",
    "finalize_recommendations"
)

builder.add_edge(
    "finalize_recommendations",
    END
)

app = builder.compile()


# =============================================
# OPTIONAL TERMINAL TEST
# =============================================

async def _smoke_test():

    result = await app.ainvoke({

        "user_request": (
            "Find cafes around my starting point"
        ),

        "mode_override": "activities",

        "origin_lat": 19.1176,
        "origin_lon": 72.9060,

        "search_radius_m": 6000,

        "travel_mode": "drive",

        "preference_overrides": {
            "available_minutes": 180,

            "budget_per_person_inr": 500,

            "group_type": "friends"
        }
    })

    print(
        "Mode:",
        result.get("selected_mode")
    )

    print(
        "Summary:",
        (
            result.get("final_response")
            or {}
        ).get("summary")
    )


if __name__ == "__main__":
    asyncio.run(_smoke_test())
