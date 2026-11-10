
"""Optional live Geoapify discovery test."""

import asyncio

from location_discovery import (
    geocode_address,
    search_places_around
)


async def main():

    address = (
        "Hiranandani Gardens, Powai, Mumbai"
    )

    print(
        "Resolving address:",
        address
    )

    origin = geocode_address(
        address
    )

    print(
        "Resolved address:",
        origin["formatted_address"]
    )

    print(
        "Coordinates:",
        origin["latitude"],
        origin["longitude"]
    )

    result = await search_places_around(
        latitude=origin["latitude"],
        longitude=origin["longitude"],
        category="cafe",
        radius_m=6000,
        limit=10
    )

    if result.get("error"):

        print(
            "ERROR:",
            result["error"]
        )

        return

    print("\nNearby cafes:")

    for place in result["places"]:

        print(
            f"{place['name']} | "
            f"{place['straight_line_km']} km "
            "straight-line"
        )

    print(
        "\nNamed cafes found:",
        len(result["places"])
    )


if __name__ == "__main__":
    asyncio.run(main())
