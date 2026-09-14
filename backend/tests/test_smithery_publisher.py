import asyncio
import json

import httpx

from product_to_mcp.smithery.publisher import SmitheryPublisher


def test_smithery_publisher_sends_metadata_before_release() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/releases"):
            return httpx.Response(202, json={"status": "WORKING", "mcpUrl": "https://mcp.example.com/mcp"})
        return httpx.Response(200, json={"ok": True})

    publisher = SmitheryPublisher("https://api.smithery.test", transport=httpx.MockTransport(handler))
    result = asyncio.run(
        publisher.publish(
            api_key="smithery-key",
            qualified_name="@acme/demo-store-mcp",
            mcp_url="https://mcp.example.com/mcp",
            display_name="Demo Store MCP",
            description="Focused MCP actions for the Demo Store product API.",
            homepage="https://example.com",
            icon_url="https://example.com/icon.png",
            repository_url="https://github.com/acme/demo",
            license="MIT",
        )
    )

    assert result["status"] == "WORKING"
    assert [request.method for request in requests] == ["PUT", "PATCH", "PUT"]
    assert [request.url.raw_path.decode("utf-8") for request in requests] == [
        "/servers/@acme%2Fdemo-store-mcp",
        "/servers/@acme%2Fdemo-store-mcp",
        "/servers/@acme%2Fdemo-store-mcp/releases",
    ]
    assert requests[0].headers["authorization"] == "Bearer smithery-key"
    assert json.loads(requests[0].content) == {
        "displayName": "Demo Store MCP",
        "description": "Focused MCP actions for the Demo Store product API.",
    }
    metadata = json.loads(requests[1].content)
    assert metadata["homepage"] == "https://example.com"
    assert metadata["iconUrl"] == "https://example.com/icon.png"
    assert metadata["repositoryUrl"] == "https://github.com/acme/demo"
    assert metadata["license"] == "MIT"
    assert metadata["unlisted"] is False
    assert b'"configSchema"' in requests[2].content
    assert b'"additionalProperties": false' in requests[2].content
