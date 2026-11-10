
import asyncio
import json

from mcp import Client
from mcp_server import mcp


async def main():
    async with Client(mcp) as client:

        result = await client.call_tool(
            "get_travel_estimate",
            {
                "origin_lat": 19.0596,
                "origin_lon": 72.8295,
                "destination_lat": 19.0178,
                "destination_lon": 72.8478,
                "mode": "drive"
            }
        )

        if result.is_error:
            print("MCP tool error:", result.content)
            return

        data = result.structured_content

        if data is None:
            for item in result.content:
                if hasattr(item, "text"):
                    print(item.text)
            return

        print(json.dumps(data, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
