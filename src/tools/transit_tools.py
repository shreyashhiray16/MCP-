"""
src/tools/transit_tools.py

The 8 core MCP tools for Pune Transit and Commute.
Handlers stay thin and delegate to the service layer.
Every tool has detailed model-friendly descriptions and structured responses.
"""

from typing import Dict, Any, Optional, List
from ..services.places import resolve_place as svc_resolve_place, save_place as svc_save_place, list_saved_places as svc_list_saved_places
from ..services.stops import find_nearby_stops as svc_find_nearby_stops
from ..services.departures import next_departures as svc_next_departures, find_routes_between as svc_find_routes_between
from ..services.planner import plan_trip as svc_plan_trip
from ..adapters.metro_adapter import default_metro_adapter


async def resolve_place_tool(query: str) -> Dict[str, Any]:
    """
    Turns a Pune locality, area, landmark, or saved place into geographic coordinates.

    When to use:
    - Whenever the user mentions a location name (e.g. "Pimpri", "Hinjewadi Phase 1", "Swargate", "home").
    - Use this before calling find_nearby_stops or plan_trip if you need coordinates.

    What it does NOT do:
    - Does NOT return bus routes or timetables.
    - Does NOT handle places outside the Pune / Pimpri-Chinchwad region.
    """
    return await svc_resolve_place(query)


def find_nearby_stops_tool(
    lat: float,
    lng: float,
    radius_m: int = 500,
    mode: str = "any",
    limit: int = 10
) -> Dict[str, Any]:
    """
    Finds bus stops and Pune Metro stations near a given coordinate.

    When to use:
    - To discover what transit options exist near a user's location or landmark.
    - Before calling next_departures to get the correct stop_id.

    Parameters:
    - lat: Latitude in Pune (approx 18.4 to 18.7)
    - lng: Longitude in Pune (approx 73.7 to 74.0)
    - radius_m: Search radius in meters (50 to 2000, default 500)
    - mode: Filter mode: 'bus', 'metro', or 'any' (default 'any')
    - limit: Maximum stops to return (1 to 20, default 10)
    """
    return svc_find_nearby_stops(lat, lng, radius_m=radius_m, mode=mode, limit=limit)


def next_departures_tool(
    stop_id: str,
    route: Optional[str] = None,
    after: Optional[str] = None,
    limit: int = 5
) -> Dict[str, Any]:
    """
    Returns upcoming scheduled bus or metro departures from a specified stop.

    When to use:
    - To answer questions like "When is the next bus from Shivajinagar?" or "Next bus towards Hinjewadi?"
    - Times are calculated in Indian Standard Time (IST).

    What it does NOT do:
    - Does NOT invent or guess timetable entries if service is closed or unavailable.
    - If no departures exist, returns a structured NO_SERVICE message.
    """
    return svc_next_departures(stop_id, route_filter=route, after=after, limit=limit)


def find_routes_between_tool(
    from_stop_id: str,
    to_stop_id: str
) -> Dict[str, Any]:
    """
    Finds direct bus routes that serve both the origin stop and the destination stop.

    When to use:
    - When asked "Which route stops at both Pimpri and Deccan?" or to verify direct bus connectivity.
    """
    return svc_find_routes_between(from_stop_id, to_stop_id)


def metro_info_tool(
    line: Optional[str] = None,
    station: Optional[str] = None,
    second_station: Optional[str] = None
) -> Dict[str, Any]:
    """
    Returns curated information about the Pune Metro (Maha-Metro):
    stations on a line, first/last trains, operational hours, and fares.

    When to use:
    - When asked about Pune Metro lines (Purple Line, Aqua Line), first/last trains, or fare between two stations.
    """
    if not default_metro_adapter.is_available:
        return {
            "error": True,
            "code": "NO_DATA",
            "message": "Pune Metro dataset is currently unavailable or failed validation.",
            "hint": "Ensure data/metro.json is present and valid."
        }

    # Case 1: Fare between two stations
    if station and second_station:
        s1 = default_metro_adapter.find_station(station)
        s2 = default_metro_adapter.find_station(second_station)
        if not s1 or not s2:
            return {
                "error": True,
                "code": "INVALID_INPUT",
                "message": f"Could not find one or both metro stations: '{station}', '{second_station}'.",
                "hint": "Check official station names (e.g. Swargate, Vanaz, Ramwadi, Civil Court, PCMC)."
            }

        fare = default_metro_adapter.calculate_fare(s1.id, s2.id)
        return {
            "data": {
                "from_station": s1.name,
                "to_station": s2.name,
                "fare_inr": fare,
                "lines_involved": list(set(s1.lines + s2.lines)),
                "requires_interchange": "civil_court" not in (s1.id, s2.id) and set(s1.lines).isdisjoint(set(s2.lines)),
                "interchange_station": "Civil Court" if set(s1.lines).isdisjoint(set(s2.lines)) else None,
                "operating_hours": "06:00 AM - 10:00 PM IST"
            },
            "source": "curated",
            "data_as_of": default_metro_adapter.data.last_verified
        }

    # Case 2: Specific station details
    if station:
        s = default_metro_adapter.find_station(station)
        if not s:
            return {
                "error": True,
                "code": "INVALID_INPUT",
                "message": f"Metro station '{station}' was not found.",
                "hint": "Available stations include PCMC, Shivajinagar, Civil Court, Swargate, Vanaz, Deccan, Ramwadi."
            }

        lines_info = []
        for lid in s.lines:
            line_obj = default_metro_adapter._lines_by_id.get(lid)
            if line_obj:
                lines_info.append({
                    "line_id": line_obj.id,
                    "name": line_obj.name,
                    "first_train": line_obj.first_train,
                    "last_train": line_obj.last_train,
                    "frequency_mins_peak": line_obj.frequency_mins_peak
                })

        return {
            "data": {
                "station": s.model_dump(),
                "operational_details": lines_info,
                "interchange": len(s.lines) > 1
            },
            "source": "curated",
            "data_as_of": default_metro_adapter.data.last_verified
        }

    # Case 3: Line details or entire network
    if line:
        l = default_metro_adapter.find_line(line)
        if not l:
            return {
                "error": True,
                "code": "INVALID_INPUT",
                "message": f"Metro line '{line}' not found.",
                "hint": "Try 'Purple Line' (Line 1: PCMC - Swargate) or 'Aqua Line' (Line 2: Vanaz - Ramwadi)."
            }

        station_names = [default_metro_adapter._stations_by_id[sid].name for sid in l.stations if sid in default_metro_adapter._stations_by_id]
        return {
            "data": {
                "line": l.model_dump(),
                "stations_list": station_names
            },
            "source": "curated",
            "data_as_of": default_metro_adapter.data.last_verified
        }

    # Default: summary of all lines
    return {
        "data": {
            "network": "Pune Maha-Metro",
            "lines": [l.model_dump() for l in default_metro_adapter.data.lines],
            "total_stations": len(default_metro_adapter.data.stations),
            "interchange": "Civil Court Interchange Station",
            "operating_hours": "06:00 AM to 10:00 PM IST"
        },
        "source": "curated",
        "data_as_of": default_metro_adapter.data.last_verified
    }


async def plan_trip_tool(
    origin: str,
    destination: str,
    depart_at: Optional[str] = None,
    arrive_by: Optional[str] = None,
    modes: Optional[List[str]] = None,
    max_walk_m: int = 1000
) -> Dict[str, Any]:
    """
    Plans ranked door-to-door multi-modal trip itineraries between two Pune locations.

    When to use:
    - To answer commute questions like "Best way from Pimpri to Hinjewadi at 9 am" or "How do I get from home to college?"
    - Evaluates direct buses, metro lines, multi-modal transfers, and walking legs.

    What it does NOT do:
    - Does NOT book tickets or process payments (strictly informational).
    - If no transit service exists, reports NO_SERVICE rather than guessing.
    """
    return await svc_plan_trip(
        origin=origin,
        destination=destination,
        depart_at=depart_at,
        arrive_by=arrive_by,
        modes=modes,
        max_walk_m=max_walk_m
    )


async def save_place_tool(
    label: str,
    place: str
) -> Dict[str, Any]:
    """
    Saves a named favorite place (e.g. 'home', 'office', 'college') for personal commute planning.

    When to use:
    - When the user asks "Remember Hinjewadi Phase 1 as my office" or "Save DY Patil Pimpri as my college".
    """
    return await svc_save_place(label, place)


def list_saved_places_tool() -> Dict[str, Any]:
    """
    Lists the user's saved favourite places.

    When to use:
    - To check available saved places (home, office, college) for planning trips.
    """
    return svc_list_saved_places()
