
import asyncio
import json

from mcp import Client
from mcp_server import mcp


async def main():

    async with Client(mcp) as client:

        result = await client.call_tool(
            "search_places",
            {
                "category": "cafe",
                "area": "Bandra",
                "limit": 5
            }
        )

        if result.is_error:
            print("MCP tool execution failed.")
            print(result.content)
            return

        data = result.structured_content

        print(json.dumps(data, indent=2))

        if data and data.get("places"):
            print(
                f"\nSUCCESS: Found "
                f"{len(data['places'])} Mumbai places."
            )
        else:
            print("\nNo places returned. Check the error above.")


if __name__ == "__main__":
    asyncio.run(main())
