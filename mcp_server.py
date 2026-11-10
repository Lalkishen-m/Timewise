
"""TimeWise MCP tools: legacy search, origin search, and routing."""

import os
from typing import Any

import httpx

from dotenv import load_dotenv
from mcp.server import MCPServer

from location_discovery import search_places_around

load_dotenv(override=True)

mcp = MCPServer("TimeWise Discovery")


# Existing pilot areas.
# Retained ONLY for the Plans workflow.

AREA_COORDINATES = {
    "Bandra": (19.0596, 72.8295),
    "Andheri": (19.1197, 72.8464),
    "Dadar": (19.0178, 72.8478),
    "Colaba": (18.9067, 72.8147),
    "Powai": (19.1176, 72.9060),
}


# =============================================
# LEGACY PLACE DISCOVERY
# =============================================

@mcp.tool()
async def search_places(
    category: str = "cafe",
    area: str = "Bandra",
    limit: int = 5,
) -> dict[str, Any]:

    """
    Existing neighborhood-based search.
    Kept for Plans until itinerary upgrade.
    """

    coordinates = AREA_COORDINATES.get(area)

    if coordinates is None:
        return {
            "places": [],
            "error": (
                f"Unknown pilot area: {area}"
            )
        }

    return await search_places_around(
        latitude=coordinates[0],
        longitude=coordinates[1],
        category=category,
        radius_m=4000,
        limit=limit,
    )


# =============================================
# NEW DYNAMIC ACTIVITY DISCOVERY
# =============================================

@mcp.tool()
async def search_places_near_origin(
    latitude: float,
    longitude: float,
    category: str = "cafe",
    radius_m: int = 6000,
    limit: int = 15,
) -> dict[str, Any]:

    """
    Search venues around any customer's
    starting coordinates.
    """

    return await search_places_around(
        latitude=latitude,
        longitude=longitude,
        category=category,
        radius_m=radius_m,
        limit=limit,
    )


# =============================================
# ROAD ROUTING
# =============================================

@mcp.tool()
async def get_travel_estimate(
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
    mode: str = "drive",
) -> dict[str, Any]:

    """
    Return road distance in kilometres
    and estimated travel time in minutes.
    """

    key = os.getenv("GEOAPIFY_API_KEY")

    if not key:
        return {
            "error": "GEOAPIFY_API_KEY missing"
        }

    if mode not in ("drive", "walk"):
        return {
            "error": (
                "Supported travel modes: drive, walk"
            )
        }

    try:

        async with httpx.AsyncClient(
            timeout=25
        ) as client:

            response = await client.get(
                "https://api.geoapify.com/v1/routing",

                params={
                    "waypoints": (
                        f"{origin_lat},{origin_lon}|"
                        f"{destination_lat},{destination_lon}"
                    ),

                    "mode": mode,

                    "units": "metric",

                    "apiKey": key,
                }
            )

            response.raise_for_status()

            features = (
                response.json()
                .get("features") or []
            )

    except httpx.HTTPStatusError as exc:
        return {
            "error": (
                "Routing API HTTP "
                f"{exc.response.status_code}"
            )
        }

    except httpx.RequestError:
        return {
            "error": "Routing API unavailable"
        }

    if not features:
        return {
            "error": "No route found"
        }

    route = (
        features[0].get("properties")
        or {}
    )

    seconds = route.get("time")
    metres = route.get("distance")

    if seconds is None or metres is None:
        return {
            "error": (
                "Routing result missing "
                "time or distance"
            )
        }

    return {
        "transport_mode": mode,

        "distance_km": round(
            float(metres) / 1000,
            2
        ),

        "travel_minutes": round(
            float(seconds) / 60,
            2
        ),

        "travel_seconds": float(seconds),

        "source": "Geoapify Routing API",

        "estimate_type": "route_estimate",
    }
