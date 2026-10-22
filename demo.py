"""
demo.py

Interactive live demonstration of Pune Transit MCP Server:
Executes the primary real-world user queries defined in the specification
and displays the exact tool call flows, JSON results, and formatted answers.
"""

import asyncio
import json
import sys
from src.server import create_server

# Configure UTF-8 for console output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def print_section(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


async def run_live_demo():
    server = create_server()
    print_section("PUNE TRANSIT & COMMUTE MCP - LIVE EXECUTION DEMO")

    # -------------------------------------------------------------------------
    # Scenario 1: "Which bus stops are near Pimpri station?"
    # -------------------------------------------------------------------------
    print_section("Scenario 1: Which bus stops are near Pimpri station?")
    print("1. Claude calls: resolve_place(query='Pimpri')")
    p_res = await server.call_tool("resolve_place", {"query": "Pimpri"})
    p_data = json.loads(p_res.content[0].text)["data"]
    print(f"   -> Resolved: {p_data['name']} at ({p_data['lat']}, {p_data['lon']})")

    print("\n2. Claude calls: find_nearby_stops(lat=..., lng=..., radius_m=800, mode='bus')")
    stops_res = await server.call_tool("find_nearby_stops", {
        "lat": p_data["lat"],
        "lng": p_data["lon"],
        "radius_m": 800,
        "mode": "bus"
    })
    stops_data = json.loads(stops_res.content[0].text)["data"]
    print(f"   -> Found {stops_data['count']} stops within 800m:")
    for s in stops_data["stops"]:
        print(f"      • {s['name']} (ID: {s['id']}) - {s['distance_m']}m away")

    # -------------------------------------------------------------------------
    # Scenario 2: "When is the next bus from Shivajinagar towards Hinjewadi?"
    # -------------------------------------------------------------------------
    print_section("Scenario 2: When is the next bus from Shivajinagar towards Hinjewadi?")
    print("Claude calls: next_departures(stop_id='STOP_SHIVAJINAGAR', route='100', after='2026-10-14T08:30:00+05:30')")
    dep_res = await server.call_tool("next_departures", {
        "stop_id": "STOP_SHIVAJINAGAR",
        "route": "100",
        "after": "2026-10-14T08:30:00+05:30",
        "limit": 3
    })
    dep_data = json.loads(dep_res.content[0].text)["data"]
    print(f"   -> Stop: {dep_data['stop_name']} (Scheduled Departures in IST):")
    for d in dep_data["departures"]:
        print(f"      • Route {d['route_short_name']} -> {d['headsign']} at {d['departure_time']} (in {d['wait_minutes']} mins)")

    # -------------------------------------------------------------------------
    # Scenario 3: "What are the first and last metro trains from Swargate?"
    # -------------------------------------------------------------------------
    print_section("Scenario 3: What are the first and last metro trains from Swargate?")
    print("Claude calls: metro_info(station='Swargate')")
    metro_res = await server.call_tool("metro_info", {"station": "Swargate"})
    metro_data = json.loads(metro_res.content[0].text)["data"]
    op = metro_data["operational_details"][0]
    print(f"   -> Station: {metro_data['station']['name']}")
    print(f"      • Line: {op['name']} (Line ID: {op['line_id']})")
    print(f"      • First train: {op['first_train']} AM IST")
    print(f"      • Last train: {op['last_train']} PM IST")
    print(f"      • Peak Frequency: Every {op['frequency_mins_peak']} minutes")

    # -------------------------------------------------------------------------
    # Scenario 4: "Remember Hinjewadi Phase 1 as my office" & "Save DY Patil as college"
    # -------------------------------------------------------------------------
    print_section("Scenario 4: Saving personal commute places")
    print("1. Claude calls: save_place(label='home', place='Pimpri')")
    await server.call_tool("save_place", {"label": "home", "place": "Pimpri"})
    print("2. Claude calls: save_place(label='office', place='Hinjewadi Phase 1')")
    await server.call_tool("save_place", {"label": "office", "place": "Hinjewadi Phase 1"})

    print("3. Claude calls: list_saved_places()")
    saved_res = await server.call_tool("list_saved_places", {})
    saved_places = json.loads(saved_res.content[0].text)["data"]
    for sp in saved_places:
        print(f"      • [{sp['label'].upper()}]: {sp['name']} ({sp['lat']}, {sp['lon']})")

    # -------------------------------------------------------------------------
    # Scenario 5: "Best way from home to office, leaving at 8:30 am?"
    # -------------------------------------------------------------------------
    print_section("Scenario 5: Best way from home to office, leaving at 8:30 am?")
    print("Claude calls: plan_trip(origin='home', destination='office', depart_at='2026-10-14T08:30:00+05:30')")
    plan_res = await server.call_tool("plan_trip", {
        "origin": "home",
        "destination": "office",
        "depart_at": "2026-10-14T08:30:00+05:30"
    })
    plan_data = json.loads(plan_res.content[0].text)["data"]
    print(f"   -> Found {plan_data['itineraries_count']} options (Distance: {plan_data['direct_distance_km']} km):")
    best = plan_data["itineraries"][0]
    print(f"   ★ RECOMMENDED OPTION: {best['summary']}")
    print(f"      • Total travel time: {best['total_duration_minutes']} mins")
    print(f"      • Transfers: {best['transfers']}, Walking: {best['walking_distance_m']}m")
    print("      • Journey Breakdown:")
    for leg in best["legs"]:
        if leg["mode"] == "walk":
            print(f"        - Walk from {leg['from']} to {leg['to']} ({leg['distance_m']}m, ~{leg['duration_minutes']} mins)")
        elif leg["mode"] == "bus":
            print(f"        - Bus {leg['route']} from {leg['from']} to {leg['to']} ({leg['departure_time']} -> {leg['arrival_time']})")
        elif leg["mode"] == "metro":
            print(f"        - Metro ({leg['line']}) from {leg['from']} to {leg['to']} ({leg['departure_time']} -> {leg['arrival_time']}, Fare: ₹{leg['fare_inr']})")

    road = plan_data["road_comparison"]
    orig_c = plan_data["origin"]
    dest_c = plan_data["destination"]
    print(f"\n      [Road Comparison]: Cab/Auto takes ~{road['estimated_duration_minutes']} mins (~{road['approx_fare_inr']})")
    print(f"      🗺️  Live Map Preview: http://localhost:8000/?origin=home&destination=office")
    print(f"      📍 Google Maps Route: https://www.google.com/maps/dir/?api=1&origin={orig_c['lat']},{orig_c['lon']}&destination={dest_c['lat']},{dest_c['lon']}")

    # -------------------------------------------------------------------------
    # Scenario 6: "Which route stops at both Pimpri and Deccan?"
    # -------------------------------------------------------------------------
    print_section("Scenario 6: Which route stops at both Pimpri and Deccan?")
    print("Claude calls: find_routes_between(from_stop_id='STOP_PIMPRI_STN', to_stop_id='STOP_DECCAN')")
    routes_res = await server.call_tool("find_routes_between", {
        "from_stop_id": "STOP_PIMPRI_STN",
        "to_stop_id": "STOP_DECCAN"
    })
    routes_data = json.loads(routes_res.content[0].text)["data"]
    print(f"   -> Direct Routes between {routes_data['from_stop']['name']} and {routes_data['to_stop']['name']}:")
    for r in routes_data["direct_routes"]:
        print(f"      • Route {r['route_short_name']}: {r['route_long_name']} (Headsign: {r['headsign']})")

    # -------------------------------------------------------------------------
    # Scenario 7: "What is the metro fare from Vanaz to Ramwadi?"
    # -------------------------------------------------------------------------
    print_section("Scenario 7: What is the metro fare from Vanaz to Ramwadi?")
    print("Claude calls: metro_info(station='Vanaz', second_station='Ramwadi')")
    fare_res = await server.call_tool("metro_info", {"station": "Vanaz", "second_station": "Ramwadi"})
    fare_data = json.loads(fare_res.content[0].text)["data"]
    print(f"   -> From: {fare_data['from_station']} to {fare_data['to_station']}")
    print(f"      • Fare: ₹{fare_data['fare_inr']}")
    print(f"      • Operating Hours: {fare_data['operating_hours']}")
    print(f"      • Lines involved: {', '.join(fare_data['lines_involved'])}")

    print_section("DEMO COMPLETE - ALL SCENARIOS EXECUTED SUCCESSFULLY")


if __name__ == "__main__":
    asyncio.run(run_live_demo())
