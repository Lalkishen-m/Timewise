
# smart_activity_discovery.py
# Free-source TimeWise Activity discovery
#
# Geoapify / OpenStreetMap + optional Wikipedia
# No Google Maps API key or paid search API required.

import asyncio
import math
import os
import re
from urllib.parse import quote, quote_plus

import httpx
from dotenv import load_dotenv

load_dotenv(override=True)

PLACES_URL = "https://api.geoapify.com/v2/places"
DETAILS_URL = "https://api.geoapify.com/v2/place-details"
MATRIX_URL = "https://api.geoapify.com/v1/routematrix"

# Broad Mumbai metropolitan pilot coverage.
# This boundary is not a user-selected radius.
SOUTH, NORTH = 18.85, 19.50
WEST, EAST = 72.70, 73.35

MAX_ROUTE_CANDIDATES = 16
MAX_ENRICHED = 8

CATEGORY_MAP = {
    "cafe": "catering.cafe",
    "restaurant": "catering.restaurant",
    "restobar": (
        "catering.bar,catering.pub,"
        "catering.biergarten"
    ),
    "park": "leisure.park",
    "lake": "natural.water",
    "beach": "beach",
    "museum": "entertainment.museum",
    "cinema": "entertainment.cinema",
    "attraction": "tourism.attraction",
}

DURATION_MINUTES = {
    "cafe": 75,
    "restaurant": 90,
    "restobar": 105,
    "park": 60,
    "lake": 75,
    "beach": 75,
    "museum": 90,
    "cinema": 150,
    "attraction": 90,
}

CUISINES = (
    "south indian", "north indian", "italian",
    "chinese", "japanese", "korean", "thai",
    "mexican", "continental", "maharashtrian",
    "seafood", "mediterranean", "vegetarian",
    "vegan", "biryani", "pizza",
)


def _key():
    value = os.getenv("GEOAPIFY_API_KEY")
    if not value:
        raise RuntimeError(
            "GEOAPIFY_API_KEY is missing from .env"
        )
    return value


def _request_preferences(request):
    text = request.lower()

    patterns = [
        ("restobar", r"\b(restobar|resto.bar|pub|"
         r"brewery|cocktail bar|lounge|bar)\b"),
        ("lake", r"\b(lake|lakeside|talav|talao)\b"),
        ("beach", r"\b(beach|seaside)\b"),
        ("cafe", r"\b(cafe|cafes|café|coffee|"
         r"coffee shop)\b"),
        ("restaurant", r"\b(restaurant|food|"
         r"lunch|dinner|dining)\b"),
        ("park", r"\b(park|garden|outdoor)\b"),
        ("museum", r"\bmuseum\b"),
        ("cinema", r"\b(movie|cinema|film)\b"),
    ]

    category = "attraction"

    for name, pattern in patterns:
        if re.search(pattern, text):
            category = name
            break

    quiet = bool(re.search(
        r"\b(quiet|silent|peaceful|calm|"
        r"less crowded|not noisy|serene)\b",
        text,
    ))

    cuisine = next(
        (x for x in CUISINES if x in text),
        None,
    )

    return category, quiet, cuisine


def _haversine(a, b):
    lat1, lon1 = a
    lat2, lon2 = b

    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    v = (
        math.sin(dp / 2) ** 2
        + math.cos(p1) * math.cos(p2)
        * math.sin(dl / 2) ** 2
    )

    return 12742.0176 * math.asin(
        min(1, math.sqrt(v))
    )


def _grid_filters(origin_lat, origin_lon):
    """Search across metro tiles, not five preset areas."""

    filters = []

    # 2 rows x 3 columns spread across the region.
    for row in range(2):
        south = SOUTH + row * (NORTH - SOUTH) / 2
        north = SOUTH + (row + 1) * (NORTH - SOUTH) / 2

        for col in range(3):
            west = WEST + col * (EAST - WEST) / 3
            east = WEST + (col + 1) * (EAST - WEST) / 3

            filters.append(
                f"rect:{west},{south},{east},{north}"
            )

    # An additional search prioritizes the selected
    # starting area. This is an internal search tile,
    # NOT a user-imposed outing distance limit.
    filters.insert(
        0,
        f"circle:{origin_lon},{origin_lat},12000"
    )

    return filters


async def _places_search(
    client, category, filter_value,
    origin_lat, origin_lon,
):
    response = await client.get(
        PLACES_URL,
        params={
            "categories": CATEGORY_MAP[category],
            "filter": filter_value,
            "bias": (
                f"proximity:{origin_lon},{origin_lat}"
            ),
            "limit": 20,
            "apiKey": _key(),
        },
    )
    response.raise_for_status()

    return response.json().get("features") or []


def _parse_place(feature, category, origin):
    props = feature.get("properties") or {}
    coords = (
        feature.get("geometry") or {}
    ).get("coordinates") or []

    if not props.get("name") or len(coords) < 2:
        return None

    lon, lat = float(coords[0]), float(coords[1])

    if not (
        SOUTH <= lat <= NORTH
        and WEST <= lon <= EAST
    ):
        return None

    name = props["name"]

    # A natural-water feature isn't necessarily a
    # lake; don't recommend the sea as a lake.
    if category == "lake":
        if not any(
            word in name.lower()
            for word in (
                "lake", "talav", "talao",
                "sarovar", "sagar"
            )
        ):
            return None

    return {
        "name": name,
        "category": category,
        "address": (
            props.get("formatted")
            or props.get("address_line2")
            or "Address unavailable"
        ),
        "latitude": lat,
        "longitude": lon,
        "place_id": props.get("place_id"),
        "mapped_categories": props.get(
            "categories", []
        ),
        "air_distance_km": round(
            _haversine(origin, (lat, lon)), 2
        ),
        "source": "Geoapify / OpenStreetMap",
    }


def _preliminary_quality(place):
    """Metadata completeness is NOT popularity."""

    return (
        int(bool(place["name"])) * 5
        + int(
            place["address"] != "Address unavailable"
        ) * 3
        + int(bool(place.get("place_id"))) * 3
        + min(
            len(place.get("mapped_categories") or []),
            4,
        )
        - min(place["air_distance_km"], 50) * 0.25
    )


async def _route_matrix(
    client, sources, targets, mode,
):
    payload = {
        "mode": mode,
        "sources": [
            {"location": [lon, lat]}
            for lat, lon in sources
        ],
        "targets": [
            {"location": [lon, lat]}
            for lat, lon in targets
        ],
        "units": "metric",
    }

    if mode == "drive":
        payload["traffic"] = "approximated"

    response = await client.post(
        MATRIX_URL,
        params={"apiKey": _key()},
        json=payload,
    )
    response.raise_for_status()

    return (
        response.json().get("sources_to_targets")
        or []
    )


async def _attach_routes(client, places, origin, mode):
    destinations = [
        (p["latitude"], p["longitude"])
        for p in places
    ]

    outward, returning = await asyncio.gather(
        _route_matrix(
            client, [origin], destinations, mode
        ),
        _route_matrix(
            client, destinations, [origin], mode
        ),
    )

    for index, place in enumerate(places):
        try:
            outbound = outward[0][index]
            inbound = returning[index][0]

            outbound_seconds = outbound["time"]
            inbound_seconds = inbound["time"]

            if (
                not isinstance(
                    outbound_seconds, (int, float)
                )
                or not isinstance(
                    inbound_seconds, (int, float)
                )
                or outbound_seconds <= 0
                or inbound_seconds <= 0
            ):
                continue

            place["outward_minutes"] = round(
                outbound_seconds / 60, 1
            )
            place["return_minutes"] = round(
                inbound_seconds / 60, 1
            )
            place["round_trip_minutes"] = round(
                (
                    outbound_seconds
                    + inbound_seconds
                ) / 60,
                1,
            )

            distance = outbound.get("distance")

            if isinstance(distance, (int, float)):
                place["road_distance_km"] = round(
                    distance / 1000, 1
                )

            place["route_verified"] = True

        except (
            IndexError, KeyError, TypeError, ValueError
        ):
            continue


async def _get_details(client, place):
    place_id = place.get("place_id")

    if not place_id:
        return {}

    response = await client.get(
        DETAILS_URL,
        params={
            "id": place_id,
            "features": "details",
            "apiKey": _key(),
        },
    )
    response.raise_for_status()

    features = (
        response.json().get("features") or []
    )

    for feature in features:
        props = feature.get("properties") or {}

        if props:
            return props

    return {}


async def _get_wikipedia(client, reference):
    """Use only an explicit English Wikipedia tag."""

    if not isinstance(reference, str):
        return None

    if reference.startswith("en:"):
        title = reference[3:]

    elif "en.wikipedia.org/wiki/" in reference:
        title = reference.split("/wiki/", 1)[-1]

    else:
        return None

    if not title:
        return None

    try:
        response = await client.get(
            (
                "https://en.wikipedia.org/api/rest_v1/"
                "page/summary/" + quote(title, safe="")
            ),
            headers={
                "User-Agent": (
                    "TimeWiseMVP/0.1 "
                    "(educational local prototype)"
                )
            },
            timeout=12,
        )
        response.raise_for_status()
        data = response.json()

        return {
            "summary": (
                data.get("extract") or ""
            )[:500],
            "url": (
                (data.get("content_urls") or {})
                .get("desktop", {})
                .get("page")
            ),
        }

    except (httpx.HTTPError, ValueError):
        return None


def _enrich_metadata(place, props):
    catering = props.get("catering") or {}
    raw = (
        (props.get("datasource") or {})
        .get("raw") or {}
    )

    cuisine = (
        catering.get("cuisine")
        or raw.get("cuisine")
    )

    place["cuisine"] = cuisine
    place["description"] = (
        props.get("description")
        or raw.get("description")
    )

    place["opening_hours"] = (
        props.get("opening_hours")
        or raw.get("opening_hours")
    )

    place["website"] = (
        props.get("website")
        or raw.get("website")
    )

    place["outdoor_seating"] = props.get(
        "outdoor_seating",
        raw.get("outdoor_seating"),
    )

    place["venue_type"] = {
        "cafe": "Café",
        "restaurant": "Restaurant",
        "restobar": "Bar / pub",
        "lake": "Lake / waterbody",
        "park": "Park / garden",
        "beach": "Beach",
        "cinema": "Cinema",
        "museum": "Museum",
    }.get(
        place["category"],
        "Attraction",
    )

    wiki = props.get("wiki_and_media") or {}
    place["wikipedia_reference"] = wiki.get(
        "wikipedia"
    )


def _venue_reason(place, quiet, cuisine_requested):
    """Use only actual mapped facts and estimates."""

    facts = []

    if place.get("cuisine"):
        facts.append(
            f"Mapped cuisine: {place['cuisine']}"
        )

    if place.get("description"):
        description = " ".join(
            str(place["description"]).split()
        )
        facts.append(
            f"OpenStreetMap description: "
            f"{description[:180]}"
        )

    if place.get("outdoor_seating") in (
        True, "yes"
    ):
        facts.append(
            "Outdoor seating is listed"
        )

    if place.get("outward_minutes") is not None:
        facts.append(
            f"Estimated {place['outward_minutes']:.0f} "
            "minutes away by your selected mode"
        )

    if place.get("wikipedia"):
        facts.append(
            "Additional background is available "
            "from Wikipedia"
        )

    if cuisine_requested:
        mapped = str(
            place.get("cuisine") or ""
        ).lower()

        if cuisine_requested not in mapped:
            facts.append(
                f"Requested {cuisine_requested} "
                "cuisine is not confirmed"
            )

    if quiet:
        facts.append(
            "Quiet ambience is not independently "
            "verified by customer reviews"
        )

    if not facts:
        return (
            "This mapped venue is a possible "
            "activity option, but limited verified "
            "details are available."
        )

    return ". ".join(facts) + "."


def _score(place, available, quiet, cuisine):
    """A transparent suitability score, not a rating."""

    total = place.get("outing_minutes")
    road = place.get("round_trip_minutes")

    if total is None or road is None:
        return 0

    if total > available:
        return 0

    score = 45  # Category match and known route.

    score += 15  # Estimated time fit.

    score += max(0, 20 - road / 8)

    score += 5 if place.get("opening_hours") else 0
    score += 5 if place.get("description") else 0
    score += 5 if place.get("cuisine") else 0
    score += 5 if place.get("website") else 0

    if cuisine:
        mapped = str(
            place.get("cuisine") or ""
        ).lower()

        if cuisine in mapped:
            score += 10
        else:
            score -= 10

    if quiet:
        # Do not claim quietness from category
        # or lack of review data.
        description = str(
            place.get("description") or ""
        ).lower()

        if any(
            word in description
            for word in (
                "quiet", "peaceful",
                "calm", "serene"
            )
        ):
            score += 5

    return round(
        min(100, max(0, score)), 1
    )


def _search_link(place):
    query = (
        f"{place['name']}, {place['address']}"
    )

    return (
        "https://www.google.com/maps/search/"
        "?api=1&query="
        + quote_plus(query)
    )


async def recommend_activities(
    request,
    origin_lat,
    origin_lon,
    origin_label,
    available_minutes,
    budget_inr=None,
    travel_mode="drive",
    max_results=5,
):
    """
    Find suitable activities without Google Places.

    Opening hours and costs are displayed only
    if actual source information is available.
    """

    category, quiet, cuisine = (
        _request_preferences(request)
    )

    origin = (
        float(origin_lat),
        float(origin_lon),
    )

    filters = _grid_filters(*origin)
    warnings = []

    async with httpx.AsyncClient(
        timeout=25
    ) as client:

        responses = await asyncio.gather(
            *[
                _places_search(
                    client, category, tile,
                    *origin
                )
                for tile in filters
            ],
            return_exceptions=True,
        )

        candidates_by_id = {}
        per_tile = []

        for result in responses:
            if isinstance(result, Exception):
                warnings.append(
                    "One regional discovery request failed."
                )
                continue

            tile_places = []

            for feature in result:
                place = _parse_place(
                    feature, category, origin
                )

                if place:
                    tile_places.append(place)

            per_tile.append(tile_places)

        # Round-robin selection gives broader
        # geographic coverage before routing.
        for tile_places in per_tile:
            tile_places.sort(
                key=_preliminary_quality,
                reverse=True,
            )

        for i in range(12):
            for tile_places in per_tile:
                if i >= len(tile_places):
                    continue

                place = tile_places[i]

                key = (
                    place.get("place_id")
                    or (
                        place["name"].lower(),
                        place["latitude"],
                        place["longitude"],
                    )
                )

                candidates_by_id[key] = place

        candidates = list(
            candidates_by_id.values()
        )

        candidates.sort(
            key=_preliminary_quality,
            reverse=True,
        )

        # Route a bounded set to protect
        # the free daily credit allowance.
        candidates = candidates[
            :MAX_ROUTE_CANDIDATES
        ]

        if not candidates:
            return {
                "recommended": [],
                "alternatives": [],
                "warnings": [
                    "No named venues found in "
                    "the selected category."
                ] + warnings,
                "candidates_discovered": 0,
                "mode": "activities",
            }

        for place in candidates:
            place["route_verified"] = False

        try:
            await _attach_routes(
                client, candidates,
                origin, travel_mode
            )

        except (httpx.HTTPError, RuntimeError):
            warnings.append(
                "Road routing is unavailable. "
                "Unverified journeys cannot be "
                "treated as time-fitting."
            )

        duration = DURATION_MINUTES.get(
            category, 90
        )

        for place in candidates:
            place["activity_minutes"] = duration

            if place["route_verified"]:
                place["outing_minutes"] = round(
                    place["round_trip_minutes"]
                    + duration,
                    1,
                )
                place["fits_time"] = (
                    place["outing_minutes"]
                    <= available_minutes
                )
            else:
                place["outing_minutes"] = None
                place["fits_time"] = False

        # Prefer feasible candidates but retain
        # alternatives for transparency.
        candidates.sort(
            key=lambda p: (
                p["fits_time"],
                -p.get("round_trip_minutes", 9999),
                _preliminary_quality(p),
            ),
            reverse=True,
        )

        enriched = candidates[:MAX_ENRICHED]

        for place in enriched:
            try:
                details = await _get_details(
                    client, place
                )

            except (httpx.HTTPError, ValueError):
                details = {}

            _enrich_metadata(place, details)

            wiki_reference = place.get(
                "wikipedia_reference"
            )

            if wiki_reference:
                place["wikipedia"] = (
                    await _get_wikipedia(
                        client, wiki_reference
                    )
                )

            place["price_verified"] = False
            place["price_text"] = (
                "Per-person price not verified"
            )

            place["budget_inr"] = budget_inr

            place["reason"] = _venue_reason(
                place, quiet, cuisine
            )

            place["timewise_score"] = _score(
                place,
                available_minutes,
                quiet,
                cuisine,
            )

            place["maps_url"] = _search_link(
                place
            )

        enriched.sort(
            key=lambda p: (
                p["fits_time"],
                p["timewise_score"],
                -p.get(
                    "round_trip_minutes", 9999
                ),
            ),
            reverse=True,
        )

    return {
        "mode": "activities",
        "category": category,
        "requested_quiet": quiet,
        "requested_cuisine": cuisine,
        "recommended": [
            p for p in enriched
            if p["fits_time"]
        ][:max_results],
        "alternatives": [
            p for p in enriched
            if not p["fits_time"]
        ][:3],
        "candidates_discovered": len(
            candidates_by_id
        ),
        "warnings": warnings,
        "available_minutes": available_minutes,
        "disclaimer": (
            "No Google, Zomato or Swiggy ratings "
            "were retrieved. TimeWise scores are "
            "internal suitability scores. Road "
            "travel and activity durations are "
            "estimates. Opening hours may be "
            "outdated and pricing is unverified."
        ),
    }
