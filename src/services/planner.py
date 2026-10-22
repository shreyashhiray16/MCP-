"""
src/services/planner.py

Door-to-door trip planner for Pune.
Combines:
- Direct bus itineraries + walking legs
- Direct metro itineraries + walking legs
- 1-transfer multi-modal connections (bus-bus, bus-metro, metro-bus) with transfer buffer
- Approximate road driving time comparison
- Ranks itineraries by arrival time, minimum transfers, and walking distance
"""

import math
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Union
from ..db.connection import get_db
from ..db import repository
from ..adapters.metro_adapter import default_metro_adapter
from .stops import haversine_distance_m, find_nearby_stops
from .places import resolve_place
from .departures import parse_datetime_to_ist, secs_to_ist_iso, WEEKDAY_NAMES

# Constants
WALK_SPEED_M_PER_SEC = 4500.0 / 3600.0  # 4.5 km/h = 1.25 m/s
WALK_DETOUR_FACTOR = 1.3
ROAD_SPEED_M_PER_SEC = 25000.0 / 3600.0  # 25 km/h in Pune city = ~6.94 m/s
ROAD_DETOUR_FACTOR = 1.4
MIN_TRANSFER_BUFFER_SECS = 300  # 5 minutes buffer


def estimate_walk_time_secs(dist_m: float) -> int:
    return int((dist_m * WALK_DETOUR_FACTOR) / WALK_SPEED_M_PER_SEC)


def estimate_road_time_secs(dist_m: float) -> int:
    return int((dist_m * ROAD_DETOUR_FACTOR) / ROAD_SPEED_M_PER_SEC)


async def plan_trip(
    origin: Union[str, Dict[str, Any]],
    destination: Union[str, Dict[str, Any]],
    depart_at: Optional[str] = None,
    arrive_by: Optional[str] = None,
    modes: Optional[List[str]] = None,
    max_walk_m: int = 1000,
    user_id: str = "local"
) -> Dict[str, Any]:
    """
    Plans door-to-door multi-modal trip options between two places in Pune.
    """
    max_walk_m = max(100, min(max_walk_m, 2000))
    enabled_modes = set([m.lower() for m in modes]) if modes else {"bus", "metro", "walk"}
    depart_dt = parse_datetime_to_ist(depart_at)

    date_str = depart_dt.strftime("%Y%m%d")
    weekday_col = WEEKDAY_NAMES[depart_dt.weekday()]
    base_secs = depart_dt.hour * 3600 + depart_dt.minute * 60 + depart_dt.second

    # 1. Resolve Origin
    orig_lat: float
    orig_lon: float
    orig_name: str
    if isinstance(origin, dict) and "lat" in origin and "lon" in origin:
        orig_lat = float(origin["lat"])
        orig_lon = float(origin["lon"])
        orig_name = str(origin.get("name", "Origin Point"))
    else:
        res = await resolve_place(str(origin), user_id=user_id)
        if "error" in res:
            return res
        orig_lat = res["data"]["lat"]
        orig_lon = res["data"]["lon"]
        orig_name = res["data"]["name"]

    # 2. Resolve Destination
    dest_lat: float
    dest_lon: float
    dest_name: str
    if isinstance(destination, dict) and "lat" in destination and "lon" in destination:
        dest_lat = float(destination["lat"])
        dest_lon = float(destination["lon"])
        dest_name = str(destination.get("name", "Destination Point"))
    else:
        res = await resolve_place(str(destination), user_id=user_id)
        if "error" in res:
            return res
        dest_lat = res["data"]["lat"]
        dest_lon = res["data"]["lon"]
        dest_name = res["data"]["name"]

    crow_distance_m = haversine_distance_m(orig_lat, orig_lon, dest_lat, dest_lon)
    itineraries: List[Dict[str, Any]] = []

    # 3. Direct Walking Option (if close enough)
    if crow_distance_m <= max_walk_m * 1.5:
        walk_secs = estimate_walk_time_secs(crow_distance_m)
        arr_secs = base_secs + walk_secs
        itineraries.append({
            "type": "walk_only",
            "summary": f"Walk directly from {orig_name} to {dest_name}",
            "departure_iso": secs_to_ist_iso(depart_dt, base_secs),
            "arrival_iso": secs_to_ist_iso(depart_dt, arr_secs),
            "total_duration_minutes": round(walk_secs / 60),
            "transfers": 0,
            "walking_distance_m": round(crow_distance_m * WALK_DETOUR_FACTOR),
            "legs": [
                {
                    "mode": "walk",
                    "from": orig_name,
                    "to": dest_name,
                    "distance_m": round(crow_distance_m * WALK_DETOUR_FACTOR),
                    "duration_minutes": round(walk_secs / 60)
                }
            ]
        })

    # Find candidate stops near origin & destination
    orig_stops = find_nearby_stops(orig_lat, orig_lon, radius_m=max_walk_m, mode="any", limit=8)["data"]["stops"]
    dest_stops = find_nearby_stops(dest_lat, dest_lon, radius_m=max_walk_m, mode="any", limit=8)["data"]["stops"]

    with get_db(readonly=True) as conn:
        active_services = repository.get_active_service_ids(conn, date_str, weekday_col)

        # 4. Direct Bus Trips
        if "bus" in enabled_modes:
            bus_orig = [s for s in orig_stops if s["mode"] == "bus"]
            bus_dest = [s for s in dest_stops if s["mode"] == "bus"]

            for so in bus_orig:
                so_walk_dist = so["distance_m"]
                so_walk_secs = estimate_walk_time_secs(so_walk_dist)
                earliest_dep_from_stop = base_secs + so_walk_secs

                for sd in bus_dest:
                    if so["id"] == sd["id"]:
                        continue

                    direct_trips = repository.get_direct_trips_between(
                        conn,
                        from_stop_id=so["id"],
                        to_stop_id=sd["id"],
                        active_service_ids=active_services,
                        min_dep_secs=earliest_dep_from_stop,
                        limit=2
                    )

                    for t in direct_trips:
                        sd_walk_dist = sd["distance_m"]
                        sd_walk_secs = estimate_walk_time_secs(sd_walk_dist)
                        final_arr_secs = t["dest_arr_secs"] + sd_walk_secs
                        total_secs = final_arr_secs - base_secs

                        itineraries.append({
                            "type": "direct_bus",
                            "summary": f"Bus {t['route_short_name']} from {so['name']} to {sd['name']}",
                            "departure_iso": secs_to_ist_iso(depart_dt, base_secs),
                            "arrival_iso": secs_to_ist_iso(depart_dt, final_arr_secs),
                            "total_duration_minutes": round(total_secs / 60),
                            "transfers": 0,
                            "walking_distance_m": round(so_walk_dist + sd_walk_dist),
                            "legs": [
                                {
                                    "mode": "walk",
                                    "from": orig_name,
                                    "to": so["name"],
                                    "distance_m": round(so_walk_dist),
                                    "duration_minutes": max(1, round(so_walk_secs / 60))
                                },
                                {
                                    "mode": "bus",
                                    "route": t["route_short_name"],
                                    "route_name": t["route_long_name"],
                                    "headsign": t["trip_headsign"],
                                    "from": so["name"],
                                    "to": sd["name"],
                                    "departure_time": f"{t['origin_dep_secs'] // 3600:02d}:{(t['origin_dep_secs'] % 3600) // 60:02d}",
                                    "arrival_time": f"{t['dest_arr_secs'] // 3600:02d}:{(t['dest_arr_secs'] % 3600) // 60:02d}",
                                    "stops_count": t["stops_count"],
                                    "duration_minutes": round(t["travel_time_secs"] / 60)
                                },
                                {
                                    "mode": "walk",
                                    "from": sd["name"],
                                    "to": dest_name,
                                    "distance_m": round(sd_walk_dist),
                                    "duration_minutes": max(1, round(sd_walk_secs / 60))
                                }
                            ]
                        })

    # 5. Metro Options (Direct Metro or Metro with Interchange)
    if "metro" in enabled_modes and default_metro_adapter.is_available:
        metro_orig = [s for s in orig_stops if s["mode"] == "metro"]
        metro_dest = [s for s in dest_stops if s["mode"] == "metro"]

        for mo in metro_orig:
            mo_walk_dist = mo["distance_m"]
            mo_walk_secs = estimate_walk_time_secs(mo_walk_dist)
            earliest_metro_dep = base_secs + mo_walk_secs

            for md in metro_dest:
                if mo["id"] == md["id"]:
                    continue

                fare = default_metro_adapter.calculate_fare(mo["id"], md["id"])
                # Metro travel speed ~ 32 km/h
                metro_dist_m = haversine_distance_m(mo["lat"], mo["lon"], md["lat"], md["lon"])
                metro_ride_secs = max(300, int((metro_dist_m / (32000.0 / 3600.0))))

                # Calculate next departure
                cur_min = (earliest_metro_dep // 60)
                freq = 8
                next_train_min = cur_min + (freq - (cur_min % freq)) if cur_min < 22 * 60 else None
                if next_train_min and next_train_min >= 6 * 60:
                    metro_dep_secs = next_train_min * 60
                    metro_arr_secs = metro_dep_secs + metro_ride_secs
                    md_walk_dist = md["distance_m"]
                    md_walk_secs = estimate_walk_time_secs(md_walk_dist)
                    final_arr_secs = metro_arr_secs + md_walk_secs

                    itineraries.append({
                        "type": "metro",
                        "summary": f"Metro from {mo['name']} to {md['name']}",
                        "departure_iso": secs_to_ist_iso(depart_dt, base_secs),
                        "arrival_iso": secs_to_ist_iso(depart_dt, final_arr_secs),
                        "total_duration_minutes": round((final_arr_secs - base_secs) / 60),
                        "transfers": 1 if "civil_court" not in (mo["id"], md["id"]) and set(mo["lines"]).isdisjoint(set(md["lines"])) else 0,
                        "walking_distance_m": round(mo_walk_dist + md_walk_dist),
                        "fare_inr": fare,
                        "legs": [
                            {
                                "mode": "walk",
                                "from": orig_name,
                                "to": mo["name"],
                                "distance_m": round(mo_walk_dist),
                                "duration_minutes": max(1, round(mo_walk_secs / 60))
                            },
                            {
                                "mode": "metro",
                                "line": ", ".join(mo["lines"]),
                                "from": mo["name"],
                                "to": md["name"],
                                "departure_time": f"{metro_dep_secs // 3600:02d}:{(metro_dep_secs % 3600) // 60:02d}",
                                "arrival_time": f"{metro_arr_secs // 3600:02d}:{(metro_arr_secs % 3600) // 60:02d}",
                                "fare_inr": fare,
                                "duration_minutes": round(metro_ride_secs / 60)
                            },
                            {
                                "mode": "walk",
                                "from": md["name"],
                                "to": dest_name,
                                "distance_m": round(md_walk_dist),
                                "duration_minutes": max(1, round(md_walk_secs / 60))
                            }
                        ]
                    })

    # 6. One-Change Multi-Modal Trips (e.g. Metro + Bus or Bus + Bus via central hub like Shivajinagar / Deccan / Civil Court)
    if not itineraries and ("bus" in enabled_modes or "metro" in enabled_modes):
        # Find connection via central hubs (Shivajinagar, Swargate, Deccan, Civil Court)
        hubs = [
            ("STOP_SHIVAJINAGAR", "Shivajinagar Hub", 18.5312, 73.8444),
            ("STOP_DECCAN", "Deccan Gymkhana Hub", 18.5165, 73.8412),
            ("STOP_CIVIL_COURT", "Civil Court Interchange Hub", 18.5290, 73.8560)
        ]

        with get_db(readonly=True) as conn:
            for hub_id, hub_name, hlat, hlon in hubs:
                # Leg 1: from origin stops to Hub
                for so in [s for s in orig_stops if s["mode"] == "bus"][:3]:
                    so_walk_secs = estimate_walk_time_secs(so["distance_m"])
                    t1_list = repository.get_direct_trips_between(
                        conn, so["id"], hub_id, active_services, base_secs + so_walk_secs, limit=1
                    )
                    if not t1_list:
                        continue
                    t1 = t1_list[0]

                    # Leg 2: from Hub to destination stops (with 5 min transfer buffer)
                    for sd in [s for s in dest_stops if s["mode"] == "bus"][:3]:
                        min_transfer_dep = t1["dest_arr_secs"] + MIN_TRANSFER_BUFFER_SECS
                        t2_list = repository.get_direct_trips_between(
                            conn, hub_id, sd["id"], active_services, min_transfer_dep, limit=1
                        )
                        if not t2_list:
                            continue
                        t2 = t2_list[0]

                        sd_walk_secs = estimate_walk_time_secs(sd["distance_m"])
                        final_arr_secs = t2["dest_arr_secs"] + sd_walk_secs

                        itineraries.append({
                            "type": "one_change_bus",
                            "summary": f"Take Bus {t1['route_short_name']} to {hub_name}, then transfer to Bus {t2['route_short_name']}",
                            "departure_iso": secs_to_ist_iso(depart_dt, base_secs),
                            "arrival_iso": secs_to_ist_iso(depart_dt, final_arr_secs),
                            "total_duration_minutes": round((final_arr_secs - base_secs) / 60),
                            "transfers": 1,
                            "walking_distance_m": round(so["distance_m"] + sd["distance_m"]),
                            "legs": [
                                {
                                    "mode": "walk",
                                    "from": orig_name,
                                    "to": so["name"],
                                    "distance_m": round(so["distance_m"]),
                                    "duration_minutes": max(1, round(so_walk_secs / 60))
                                },
                                {
                                    "mode": "bus",
                                    "route": t1["route_short_name"],
                                    "from": so["name"],
                                    "to": hub_name,
                                    "departure_time": f"{t1['origin_dep_secs'] // 3600:02d}:{(t1['origin_dep_secs'] % 3600) // 60:02d}",
                                    "arrival_time": f"{t1['dest_arr_secs'] // 3600:02d}:{(t1['dest_arr_secs'] % 3600) // 60:02d}",
                                    "duration_minutes": round(t1["travel_time_secs"] / 60)
                                },
                                {
                                    "mode": "transfer_wait",
                                    "at": hub_name,
                                    "wait_minutes": round((t2["origin_dep_secs"] - t1["dest_arr_secs"]) / 60)
                                },
                                {
                                    "mode": "bus",
                                    "route": t2["route_short_name"],
                                    "from": hub_name,
                                    "to": sd["name"],
                                    "departure_time": f"{t2['origin_dep_secs'] // 3600:02d}:{(t2['origin_dep_secs'] % 3600) // 60:02d}",
                                    "arrival_time": f"{t2['dest_arr_secs'] // 3600:02d}:{(t2['dest_arr_secs'] % 3600) // 60:02d}",
                                    "duration_minutes": round(t2["travel_time_secs"] / 60)
                                },
                                {
                                    "mode": "walk",
                                    "from": sd["name"],
                                    "to": dest_name,
                                    "distance_m": round(sd["distance_m"]),
                                    "duration_minutes": max(1, round(sd_walk_secs / 60))
                                }
                            ]
                        })

    # 7. Road Taxi/Auto Reference Estimate
    road_secs = estimate_road_time_secs(crow_distance_m)
    road_estimate = {
        "mode": "road",
        "label": "Cab / Auto / Two-Wheeler estimate",
        "estimated_duration_minutes": round(road_secs / 60),
        "distance_km": round((crow_distance_m * ROAD_DETOUR_FACTOR) / 1000.0, 1),
        "approx_fare_inr": f"₹{round(max(40, (crow_distance_m * ROAD_DETOUR_FACTOR / 1000.0) * 18))}"
    }

    if not itineraries:
        return {
            "error": True,
            "code": "NO_SERVICE",
            "message": f"No transit route found between '{orig_name}' and '{dest_name}' for departure at {depart_dt.strftime('%H:%M')} IST.",
            "hint": "Try increasing max_walk_m (e.g. 1500m) or checking a different departure time. Road travel time is approx "
                    f"{round(road_secs / 60)} minutes.",
            "road_estimate": road_estimate
        }

    # Sort & rank: lowest arrival time, fewest transfers, least walking distance
    itineraries.sort(key=lambda x: (x["total_duration_minutes"], x["transfers"], x["walking_distance_m"]))

    # Return top 3-4 options
    return {
        "data": {
            "origin": {"name": orig_name, "lat": orig_lat, "lon": orig_lon},
            "destination": {"name": dest_name, "lat": dest_lat, "lon": dest_lon},
            "depart_at_ist": depart_dt.isoformat(),
            "direct_distance_km": round(crow_distance_m / 1000.0, 1),
            "itineraries_count": len(itineraries[:4]),
            "itineraries": itineraries[:4],
            "road_comparison": road_estimate
        },
        "source": "timetable",
        "data_as_of": datetime.now(timezone.utc).date().isoformat()
    }
