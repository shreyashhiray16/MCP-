"""
src/server.py

Pune Transit and Commute MCP Server.
Exposes tools, resources, and prompts over Model Context Protocol (MCP).
Supports stdio transport for local use with Claude Desktop and MCP Inspector.
All logging is directed strictly to stderr to keep stdout clean for JSON-RPC messages.
"""

import logging
import sys
from typing import Optional, List, Dict, Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from .tools.transit_tools import (
    resolve_place_tool,
    find_nearby_stops_tool,
    next_departures_tool,
    find_routes_between_tool,
    metro_info_tool,
    plan_trip_tool,
    save_place_tool,
    list_saved_places_tool,
)
from .resources.transit_resources import (
    get_routes_resource,
    get_stop_resource,
    get_metro_resource,
    get_user_places_resource,
)
from .prompts.transit_prompts import (
    prompt_morning_commute,
    prompt_explore_area,
)

# Configure logging strictly to stderr
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("pune_transit")


def create_server() -> MCPServer:
    """
    Factory creating and configuring the Pune Transit MCP Server.
    """
    server = MCPServer(name="pune-transit", version="0.1.0")

    # =========================================================================
    # TOOLS REGISTRATION
    # =========================================================================

    @server.tool(
        name="resolve_place",
        title="Resolve a Pune Place",
        description=(
            "Turns a Pune place name, locality, landmark, or saved place into geographic coordinates. "
            "Returns coordinates or candidates if the name is ambiguous. "
            "When to use: Whenever a place name (like 'Pimpri', 'Hinjewadi', 'Swargate', 'home') is mentioned. "
            "What it does NOT do: Does NOT return timetables or routes."
        ),
        annotations=ToolAnnotations(read_only=True)
    )
    async def resolve_place(query: str) -> Dict[str, Any]:
        return await resolve_place_tool(query)

    @server.tool(
        name="find_nearby_stops",
        title="Find Nearby Transit Stops",
        description=(
            "Lists public bus stops and Pune Metro stations near a given coordinate. "
            "When to use: To find transit options within walking distance of an area or coordinate. "
            "Parameters: lat, lng, radius_m (50..2000), mode ('bus'|'metro'|'any'), limit (1..20)."
        ),
        annotations=ToolAnnotations(read_only=True)
    )
    def find_nearby_stops(
        lat: float,
        lng: float,
        radius_m: int = 500,
        mode: str = "any",
        limit: int = 10
    ) -> Dict[str, Any]:
        return find_nearby_stops_tool(lat, lng, radius_m=radius_m, mode=mode, limit=limit)

    @server.tool(
        name="next_departures",
        title="Upcoming Transit Departures",
        description=(
            "Returns upcoming scheduled departures at a bus stop or metro station from official timetables. "
            "Times are calculated in Indian Standard Time (IST). "
            "When to use: When asked 'When is the next bus from X?' or 'When does the next train leave?'. "
            "Never guesses missing data: returns NO_SERVICE if no trips are scheduled."
        ),
        annotations=ToolAnnotations(read_only=True)
    )
    def next_departures(
        stop_id: str,
        route: Optional[str] = None,
        after: Optional[str] = None,
        limit: int = 5
    ) -> Dict[str, Any]:
        return next_departures_tool(stop_id, route=route, after=after, limit=limit)

    @server.tool(
        name="find_routes_between",
        title="Find Routes Between Stops",
        description=(
            "Finds direct bus routes that serve both origin and destination stops in travel direction order. "
            "When to use: When asked 'Which route connects Pimpri and Deccan?' or to find direct bus options."
        ),
        annotations=ToolAnnotations(read_only=True)
    )
    def find_routes_between(from_stop_id: str, to_stop_id: str) -> Dict[str, Any]:
        return find_routes_between_tool(from_stop_id, to_stop_id)

    @server.tool(
        name="metro_info",
        title="Pune Metro Information and Fares",
        description=(
            "Returns stations on a line, first and last train timings (06:00 to 22:00 IST), and official fares. "
            "When to use: For any questions regarding Pune Metro Purple Line (PCMC - Swargate), "
            "Aqua Line (Vanaz - Ramwadi), Civil Court interchange, or fare calculations."
        ),
        annotations=ToolAnnotations(read_only=True)
    )
    def metro_info(
        line: Optional[str] = None,
        station: Optional[str] = None,
        second_station: Optional[str] = None
    ) -> Dict[str, Any]:
        return metro_info_tool(line=line, station=station, second_station=second_station)

    @server.tool(
        name="plan_trip",
        title="Plan Door-to-Door Commute",
        description=(
            "Calculates ranked door-to-door multi-modal trip options (direct bus, metro, 1-transfer connections, "
            "and walking legs) with travel time and road travel comparisons. "
            "Times are in IST. "
            "What it does NOT do: Does NOT book tickets or handle payments. Strictly informational."
        ),
        annotations=ToolAnnotations(read_only=True)
    )
    async def plan_trip(
        origin: str,
        destination: str,
        depart_at: Optional[str] = None,
        arrive_by: Optional[str] = None,
        modes: Optional[List[str]] = None,
        max_walk_m: int = 1000
    ) -> Dict[str, Any]:
        return await plan_trip_tool(
            origin=origin,
            destination=destination,
            depart_at=depart_at,
            arrive_by=arrive_by,
            modes=modes,
            max_walk_m=max_walk_m
        )

    @server.tool(
        name="save_place",
        title="Save a Favorite Place",
        description=(
            "Saves a named place (e.g. 'home', 'office', 'college') for personal commute planning. "
            "When to use: When the user asks 'Remember X as my home' or 'Save Y as my college'."
        ),
        annotations=ToolAnnotations(read_only=False)
    )
    async def save_place(label: str, place: str) -> Dict[str, Any]:
        return await save_place_tool(label, place)

    @server.tool(
        name="list_saved_places",
        title="List Saved Places",
        description=(
            "Returns the list of previously saved favourite places for the user. "
            "When to use: To inspect saved places before trip planning."
        ),
        annotations=ToolAnnotations(read_only=True)
    )
    def list_saved_places() -> Dict[str, Any]:
        return list_saved_places_tool()

    # =========================================================================
    # RESOURCES REGISTRATION
    # =========================================================================

    @server.resource(
        "transit://pune/routes",
        name="pune_routes",
        title="All Pune Bus Routes",
        description="Static list of all public bus routes operating in Pune and Pimpri-Chinchwad.",
        mime_type="application/json"
    )
    def resource_routes() -> str:
        return get_routes_resource()

    @server.resource(
        "transit://pune/stops/{stop_id}",
        name="pune_stop_details",
        title="Bus Stop Details and Serving Routes",
        description="Information about a specific bus stop and the routes that call at it.",
        mime_type="application/json"
    )
    def resource_stop(stop_id: str) -> str:
        return get_stop_resource(stop_id)

    @server.resource(
        "transit://pune/metro",
        name="pune_metro_network",
        title="Pune Metro Network and Stations",
        description="Complete Pune Metro operational lines, stations, first/last trains, and fare slabs.",
        mime_type="application/json"
    )
    def resource_metro() -> str:
        return get_metro_resource()

    @server.resource(
        "transit://user/places",
        name="user_saved_places",
        title="User Saved Commute Places",
        description="User saved favourite places (home, office, college).",
        mime_type="application/json"
    )
    def resource_places() -> str:
        return get_user_places_resource()

    # =========================================================================
    # PROMPTS REGISTRATION
    # =========================================================================

    @server.prompt(
        name="morning_commute",
        title="Morning Commute Assistant",
        description="Compares commute options between saved places and recommends the best option."
    )
    def prompt_commute(origin_label: str, destination_label: str, depart_time: str) -> str:
        return prompt_morning_commute(origin_label, destination_label, depart_time)

    @server.prompt(
        name="explore_area",
        title="Explore Transit in Area",
        description="Summarizes bus stops, routes, and metro stations serving a Pune neighbourhood."
    )
    def prompt_area(area: str) -> str:
        return prompt_explore_area(area)

    return server


def main():
    """Stdio entrypoint for Claude Desktop and MCP Inspector."""
    server = create_server()
    logger.info("Starting Pune Transit MCP Server on stdio...")
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
