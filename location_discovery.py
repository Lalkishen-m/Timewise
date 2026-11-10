
"""TimeWise: Mumbai address lookup and landmark suggestions."""

import math
import os
import re
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv(override=True)

GEOCODE_URL = (
    "https://api.geoapify.com/v1/geocode/search"
)
AUTOCOMPLETE_URL = (
    "https://api.geoapify.com/v1/geocode/autocomplete"
)
PLACES_URL = "https://api.geoapify.com/v2/places"

# Approximate Mumbai pilot area.
# west longitude, south latitude, east longitude, north latitude
MUMBAI_RECT = (72.70, 18.85, 73.10, 19.40)
MUMBAI_CENTER = (19.0760, 72.8777)

CATEGORY_MAP = {
    "cafe": "catering.cafe",
    "restaurant": "catering.restaurant",
    "park": "leisure.park",
    "cinema": "entertainment.cinema",
    "museum": "entertainment.museum",
    "attraction": "tourism.attraction",
}

LANDMARK_CATEGORIES = ",".join([
    "public_transport.train",
    "public_transport.subway",
    "commercial.shopping_mall",
    "leisure.park",
    "religion.place_of_worship",
    "education.school",
    "tourism.sights",
    "entertainment.culture",
])

GENERIC_PARTS = {"mumbai", "maharashtra", "india"}

GENERIC_WORDS = {
    "society", "chs", "housing", "building",
    "apartments", "apartment", "near",
    "road", "street", "the", "co", "op",
}


def _key() -> str:
    key = os.getenv("GEOAPIFY_API_KEY")

    if not key:
        raise RuntimeError(
            "GEOAPIFY_API_KEY is missing from .env"
        )

    return key


def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)

    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1) * math.cos(p2)
        * math.sin(dl / 2) ** 2
    )

    return (
        2 * 6371.0088
        * math.asin(min(1.0, math.sqrt(a)))
    )


def _inside_mumbai(lat: float, lon: float) -> bool:
    west, south, east, north = MUMBAI_RECT

    return (
        south <= lat <= north
        and west <= lon <= east
    )


def _filter_mumbai() -> str:
    west, south, east, north = MUMBAI_RECT

    return (
        f"rect:{west},{south},{east},{north}"
        "|countrycode:in"
    )


def _words(value: str) -> set[str]:
    return set(
        re.findall(r"[a-z0-9]+", value.casefold())
    )


def _api_get(url: str, params: dict) -> dict:
    try:
        with httpx.Client(timeout=20) as client:
            response = client.get(
                url,
                params={
                    **params,
                    "apiKey": _key(),
                },
            )

            response.raise_for_status()
            return response.json()

    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"Geoapify returned HTTP "
            f"{exc.response.status_code}. "
            "Check the API key, quota and parameters."
        ) from None

    except (httpx.RequestError, ValueError):
        raise RuntimeError(
            "Could not retrieve valid Geoapify results."
        ) from None


def _geocode(
    text: str,
    *,
    lat: float | None = None,
    lon: float | None = None,
    autocomplete: bool = False,
) -> list[dict]:

    if lat is None or lon is None:
        search_filter = _filter_mumbai()
        bias = (
            f"proximity:{MUMBAI_CENTER[1]},"
            f"{MUMBAI_CENTER[0]}"
        )
    else:
        search_filter = (
            f"circle:{lon},{lat},4500"
            "|countrycode:in"
        )
        bias = f"proximity:{lon},{lat}"

    params = {
        "text": text,
        "format": "json",
        "filter": search_filter,
        "bias": bias,
        "limit": 10,
    }

    url = (
        AUTOCOMPLETE_URL
        if autocomplete
        else GEOCODE_URL
    )

    return (
        _api_get(url, params).get("results")
        or []
    )


def _valid(result: dict) -> bool:
    try:
        lat = float(result["lat"])
        lon = float(result["lon"])

        return (
            math.isfinite(lat)
            and math.isfinite(lon)
            and _inside_mumbai(lat, lon)
        )

    except (KeyError, TypeError, ValueError):
        return False


def _result_text(result: dict) -> str:
    return " ".join(
        str(result.get(key) or "")
        for key in (
            "name",
            "formatted",
            "address_line1",
            "suburb",
            "district",
            "city",
        )
    )


def _locate_locality(locality: str) -> dict:
    query = (
        f"{locality}, Mumbai, Maharashtra, India"
    )

    requested = _words(locality)

    results = _geocode(query)

    if not results:
        results = _geocode(
            query,
            autocomplete=True,
        )

    matches = []

    for item in results:
        if not _valid(item):
            continue

        if not requested.issubset(
            _words(_result_text(item))
        ):
            continue

        rank = item.get("rank") or {}

        confidence = float(
            rank.get("confidence") or 0
        )

        good_type = (
            item.get("result_type")
            in {"suburb", "district", "postcode"}
        )

        matches.append((
            int(good_type),
            confidence,
            item,
        ))

    if not matches:
        raise ValueError(
            f"Couldn't locate '{locality}' in Mumbai. "
            "Enter 'Landmark, Locality, Mumbai', "
            "for example, 'Om Yogini Society, "
            "Malad West, Mumbai'."
        )

    best = max(
        matches,
        key=lambda x: (x[0], x[1]),
    )

    return best[2]


def _option(
    name: str,
    address: str,
    lat: float,
    lon: float,
    kind: str,
    anchor_lat: float,
    anchor_lon: float,
) -> dict[str, Any]:

    return {
        "name": name,
        "formatted_address": address,
        "latitude": float(lat),
        "longitude": float(lon),
        "kind": kind,
        "distance_from_locality_km": round(
            haversine_km(
                anchor_lat,
                anchor_lon,
                lat,
                lon,
            ),
            2,
        ),
        "is_approximate_fallback": (
            kind == "locality_center"
        ),
        "source": "Geoapify",
    }


def suggest_starting_points(
    typed_address: str,
    max_options: int = 8,
) -> dict[str, Any]:
    """
    Return selectable landmarks around the
    locality inferred from the user input.

    Example:
        Om Yogini Society, Malad West, Mumbai

    Nearby landmark distances are measured
    from the locality center, not necessarily
    the exact building.
    """

    typed_address = " ".join(
        typed_address.strip().split()
    )

    if len(typed_address) < 5:
        raise ValueError(
            "Enter a landmark and locality, "
            "e.g. Om Yogini Society, Malad West, Mumbai."
        )

    max_options = max(
        2,
        min(int(max_options), 12),
    )

    parts = [
        part.strip()
        for part in typed_address.split(",")
        if part.strip()
    ]

    meaningful = [
        part
        for part in parts
        if part.casefold().strip(" .")
        not in GENERIC_PARTS
    ]

    if not meaningful:
        raise ValueError(
            "Enter a Mumbai landmark or locality."
        )

    # The last meaningful part is the locality.
    locality = meaningful[-1]
    landmark = ", ".join(meaningful[:-1])

    anchor = _locate_locality(locality)

    anchor_lat = float(anchor["lat"])
    anchor_lon = float(anchor["lon"])

    options = []
    seen_names = set()

    def add(candidate):
        if not _inside_mumbai(
            candidate["latitude"],
            candidate["longitude"],
        ):
            return

        key = candidate["name"].strip().casefold()

        if key not in seen_names:
            seen_names.add(key)
            options.append(candidate)

    # ----------------------------------------
    # 1. TRY TO FIND THE EXACT BUILDING
    # ----------------------------------------

    if landmark:
        full_query = (
            f"{landmark}, {locality}, "
            "Mumbai, Maharashtra, India"
        )

        exact_results = _geocode(
            full_query,
            lat=anchor_lat,
            lon=anchor_lon,
        )

        try:
            exact_results += _geocode(
                full_query,
                lat=anchor_lat,
                lon=anchor_lon,
                autocomplete=True,
            )
        except RuntimeError:
            pass

        distinctive = (
            _words(landmark) - GENERIC_WORDS
        )

        for result in exact_results:
            if not _valid(result):
                continue

            if result.get("result_type") not in {
                "amenity", "building"
            }:
                continue

            if not distinctive:
                continue

            if not distinctive.issubset(
                _words(_result_text(result))
            ):
                continue

            lat = float(result["lat"])
            lon = float(result["lon"])

            if haversine_km(
                anchor_lat,
                anchor_lon,
                lat,
                lon,
            ) > 4.5:
                continue

            add(_option(
                result.get("name") or landmark,
                result.get("formatted") or full_query,
                lat,
                lon,
                "exact_candidate",
                anchor_lat,
                anchor_lon,
            ))

            break

    # ----------------------------------------
    # 2. SEARCH REAL NEARBY LANDMARKS
    # ----------------------------------------

    try:
        response = _api_get(
            PLACES_URL,
            {
                "categories": LANDMARK_CATEGORIES,
                "filter": (
                    f"circle:{anchor_lon},"
                    f"{anchor_lat},3000"
                ),
                "bias": (
                    f"proximity:{anchor_lon},"
                    f"{anchor_lat}"
                ),
                "limit": 100,
            },
        )

        nearby_note = ""

    except RuntimeError as exc:
        response = {"features": []}
        nearby_note = (
            " Nearby landmark lookup was unavailable: "
            + str(exc)
        )

    nearby = []

    for feature in response.get("features") or []:
        props = (
            feature.get("properties") or {}
        )

        coords = (
            feature.get("geometry") or {}
        ).get("coordinates") or []

        if not props.get("name") or len(coords) < 2:
            continue

        lon = float(coords[0])
        lat = float(coords[1])

        if not _inside_mumbai(lat, lon):
            continue

        distance = haversine_km(
            anchor_lat,
            anchor_lon,
            lat,
            lon,
        )

        if distance > 3.05:
            continue

        nearby.append(_option(
            props["name"],
            props.get("formatted")
            or props.get("address_line2")
            or locality,
            lat,
            lon,
            "nearby_landmark",
            anchor_lat,
            anchor_lon,
        ))

    nearby.sort(
        key=lambda item: (
            item["distance_from_locality_km"]
        )
    )

    for item in nearby:
        if len(options) >= max_options - 1:
            break

        add(item)

    # ----------------------------------------
    # 3. APPROXIMATE LOCALITY FALLBACK
    # ----------------------------------------

    add(_option(
        f"{locality} (approximate locality center)",
        anchor.get("formatted")
        or f"{locality}, Mumbai",
        anchor_lat,
        anchor_lon,
        "locality_center",
        anchor_lat,
        anchor_lon,
    ))

    return {
        "typed_address": typed_address,
        "locality": locality,
        "options": options[:max_options],
        "note": (
            f"Nearby landmarks are measured from "
            f"the approximate center of {locality}, "
            "not necessarily from the exact building. "
            "Select a landmark you recognize."
            + nearby_note
        ),
    }


def geocode_address(
    address: str,
    locality_hint: str = "",
) -> dict[str, Any]:
    """Compatibility helper for earlier tests."""

    combined = (
        f"{address}, {locality_hint}"
        if locality_hint.strip()
        else address
    )

    options = suggest_starting_points(
        combined
    )["options"]

    if not options:
        raise ValueError(
            "No starting location found."
        )

    return options[0]


# ---------------------------------------------
# ACTIVITY DISCOVERY (KEEP MCP COMPATIBILITY)
# ---------------------------------------------

async def search_places_around(
    latitude: float,
    longitude: float,
    category: str = "cafe",
    radius_m: int = 6000,
    limit: int = 15,
) -> dict[str, Any]:

    if category not in CATEGORY_MAP:
        return {
            "places": [],
            "error": (
                f"Unsupported category: {category}"
            ),
        }

    if not 500 <= radius_m <= 20000:
        return {
            "places": [],
            "error": (
                "Radius must be 500–20000 metres."
            ),
        }

    try:
        async with httpx.AsyncClient(
            timeout=20
        ) as client:

            response = await client.get(
                PLACES_URL,
                params={
                    "categories": CATEGORY_MAP[category],
                    "filter": (
                        f"circle:{longitude},"
                        f"{latitude},{radius_m}"
                    ),
                    "bias": (
                        f"proximity:{longitude},"
                        f"{latitude}"
                    ),
                    "limit": max(
                        1,
                        min(int(limit), 20),
                    ),
                    "apiKey": _key(),
                },
            )

            response.raise_for_status()

            features = (
                response.json()
                .get("features") or []
            )

    except httpx.HTTPStatusError as exc:
        return {
            "places": [],
            "error": (
                f"Places API HTTP "
                f"{exc.response.status_code}"
            ),
        }

    except (httpx.RequestError, ValueError):
        return {
            "places": [],
            "error": "Places API request failed.",
        }

    places = []
    seen = set()

    for feature in features:
        props = (
            feature.get("properties") or {}
        )

        coords = (
            feature.get("geometry") or {}
        ).get("coordinates") or []

        if not props.get("name") or len(coords) < 2:
            continue

        lon = float(coords[0])
        lat = float(coords[1])

        unique = (
            props.get("place_id")
            or (
                props["name"].casefold(),
                lat,
                lon,
            )
        )

        if unique in seen:
            continue

        seen.add(unique)

        places.append({
            "name": props["name"],
            "category": category,
            "address": (
                props.get("formatted")
                or props.get("address_line2")
                or "Address unavailable"
            ),
            "latitude": lat,
            "longitude": lon,
            "place_id": props.get("place_id"),
            "source": "Geoapify / OpenStreetMap",
            "price_inr": None,
            "availability": "unknown",
            "opening_hours_verified": False,
            "straight_line_km": round(
                haversine_km(
                    latitude,
                    longitude,
                    lat,
                    lon,
                ),
                2,
            ),
        })

    return {
        "places": places,
        "error": None,
        "search_radius_m": radius_m,
    }
