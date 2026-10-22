"""
tests/test_mcp_server.py

Integration tests for the MCP Server:
- Verifies registration of 8 tools, 4 resources, 2 prompts
- Tests tool invocation through MCPServer.call_tool
- Tests resource reads through MCPServer.read_resource
- Tests prompt generation through MCPServer.get_prompt
"""

import json
import pytest
from src.server import create_server


@pytest.fixture
def mcp_server():
    return create_server()


@pytest.mark.asyncio
async def test_tools_registered(mcp_server):
    tools = await mcp_server.list_tools()
    tool_names = [t.name for t in tools]

    expected = [
        "resolve_place",
        "find_nearby_stops",
        "next_departures",
        "find_routes_between",
        "metro_info",
        "plan_trip",
        "save_place",
        "list_saved_places"
    ]
    for exp in expected:
        assert exp in tool_names, f"Expected tool '{exp}' not found in registered tools"


@pytest.mark.asyncio
async def test_call_resolve_place_tool(mcp_server):
    res = await mcp_server.call_tool("resolve_place", {"query": "Shivajinagar"})
    assert not res.is_error
    assert len(res.content) > 0
    raw_text = res.content[0].text
    payload = json.loads(raw_text)
    assert payload["data"]["name"] == "Shivajinagar"
    assert 18.5 <= payload["data"]["lat"] <= 18.6


@pytest.mark.asyncio
async def test_call_metro_info_tool(mcp_server):
    res = await mcp_server.call_tool("metro_info", {"station": "Swargate"})
    assert not res.is_error
    raw_text = res.content[0].text
    payload = json.loads(raw_text)
    assert payload["data"]["station"]["name"] == "Swargate Metro Station"


@pytest.mark.asyncio
async def test_resources_registered_and_readable(mcp_server):
    resources = await mcp_server.list_resources()
    resource_uris = [r.uri for r in resources]
    assert "transit://pune/routes" in resource_uris
    assert "transit://pune/metro" in resource_uris
    assert "transit://user/places" in resource_uris

    # Read routes resource
    read_routes = await mcp_server.read_resource("transit://pune/routes")
    assert len(read_routes) > 0
    routes_json = json.loads(read_routes[0].content)
    assert routes_json["count"] > 0

    # Read metro resource
    read_metro = await mcp_server.read_resource("transit://pune/metro")
    assert len(read_metro) > 0
    metro_json = json.loads(read_metro[0].content)
    assert "lines" in metro_json


@pytest.mark.asyncio
async def test_prompts_registered_and_rendered(mcp_server):
    prompts = await mcp_server.list_prompts()
    prompt_names = [p.name for p in prompts]
    assert "morning_commute" in prompt_names
    assert "explore_area" in prompt_names

    p = await mcp_server.get_prompt(
        "morning_commute",
        {"origin_label": "home", "destination_label": "college", "depart_time": "08:30"}
    )
    assert len(p.messages) > 0
    msg_text = p.messages[0].content.text
    assert "home" in msg_text
    assert "college" in msg_text
    assert "plan_trip" in msg_text
