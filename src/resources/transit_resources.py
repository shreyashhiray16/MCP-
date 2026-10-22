"""
src/resources/transit_resources.py

The 4 MCP resources for Pune Transit:
- transit://pune/routes: all bus routes
- transit://pune/stops/{stop_id}: one stop + routes serving it
- transit://pune/metro: metro lines and stations
- transit://user/places: saved places
"""

import json
from typing import Dict, Any
from ..db.connection import get_db
from ..db import repository
from ..adapters.metro_adapter import default_metro_adapter


def get_routes_resource() -> str:
    """Returns all public bus routes in Pune."""
    with get_db(readonly=True) as conn:
        routes = repository.get_all_routes(conn)
    return json.dumps({"routes": routes, "count": len(routes)}, indent=2)


def get_stop_resource(stop_id: str) -> str:
    """Returns details for a specific stop along with serving routes."""
    with get_db(readonly=True) as conn:
        stop = repository.get_stop_by_id(conn, stop_id)
        if not stop:
            return json.dumps({"error": f"Stop '{stop_id}' not found."}, indent=2)
        serving_routes = repository.get_routes_for_stop(conn, stop_id)

    return json.dumps({
        "stop": stop,
        "serving_routes": serving_routes,
        "routes_count": len(serving_routes)
    }, indent=2)


def get_metro_resource() -> str:
    """Returns Pune Metro operational lines, stations, and fare rules."""
    if not default_metro_adapter.is_available or not default_metro_adapter.data:
        return json.dumps({"error": "Pune Metro dataset currently unavailable."}, indent=2)

    return json.dumps(default_metro_adapter.data.model_dump(), indent=2)


def get_user_places_resource(user_id: str = "local") -> str:
    """Returns saved places for the current user."""
    with get_db(readonly=True) as conn:
        places = repository.get_user_places(conn, user_id)
    return json.dumps({"saved_places": places, "user_id": user_id}, indent=2)
