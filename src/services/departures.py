"""
src/services/departures.py

Departures service:
- Computes upcoming bus departures at a stop for IST time.
- Handles GTFS calendar active services, calendar exceptions, and trips past midnight.
- Handles metro departures when a metro station is specified.
- Implements find_routes_between for direct line checks.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from ..db.connection import get_db
from ..db import repository
from ..adapters.metro_adapter import default_metro_adapter

IST = timezone(timedelta(hours=5, minutes=30))
WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def parse_datetime_to_ist(dt_input: Optional[str]) -> datetime:
    """
    Parses ISO datetime string or returns current time in IST (UTC+5:30).
    """
    if not dt_input or not dt_input.strip():
        return datetime.now(IST)

    cleaned = dt_input.strip()
    try:
        # ISO parse
        dt = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            # Assume IST if naive
            return dt.replace(tzinfo=IST)
        return dt.astimezone(IST)
    except Exception:
        # Try HH:MM format for today
        try:
            parts = cleaned.split(":")
            now = datetime.now(IST)
            return now.replace(hour=int(parts[0]), minute=int(parts[1]), second=0, microsecond=0)
        except Exception:
            return datetime.now(IST)


def secs_to_ist_iso(base_date: datetime, secs: int) -> str:
    """Combines a base date with seconds past midnight into an IST ISO string."""
    days_add = secs // 86400
    rem_secs = secs % 86400
    hour = rem_secs // 3600
    rem = rem_secs % 3600
    minute = rem // 60
    second = rem % 60
    dt = base_date + timedelta(days=days_add)
    dt = dt.replace(hour=hour, minute=minute, second=second, microsecond=0)
    return dt.isoformat()


def next_departures(
    stop_id: str,
    route_filter: Optional[str] = None,
    after: Optional[str] = None,
    limit: int = 5
) -> Dict[str, Any]:
    """
    Fetches upcoming departures from a bus stop or metro station.
    """
    clean_stop_id = stop_id.strip()
    limit = max(1, min(limit, 10))
    query_time_ist = parse_datetime_to_ist(after)

    date_str = query_time_ist.strftime("%Y%m%d")
    weekday_col = WEEKDAY_NAMES[query_time_ist.weekday()]
    now_secs = query_time_ist.hour * 3600 + query_time_ist.minute * 60 + query_time_ist.second

    # 1. Check if this is a metro station
    metro_station = default_metro_adapter.find_station(clean_stop_id)
    if metro_station and default_metro_adapter.is_available:
        # Calculate next metro departures based on line frequencies
        first_h, first_m = 6, 0
        last_h, last_m = 22, 0
        cur_mins = query_time_ist.hour * 60 + query_time_ist.minute

        departures = []
        if cur_mins < first_h * 60:
            # First morning train
            for line_id in metro_station.lines:
                line = default_metro_adapter._lines_by_id.get(line_id)
                dep_dt = query_time_ist.replace(hour=first_h, minute=first_m, second=0)
                departures.append({
                    "route_short_name": line.name if line else line_id,
                    "headsign": f"Towards {line.stations[-1].replace('_', ' ').title()}" if line else "Terminal",
                    "departure_time": dep_dt.strftime("%H:%M:%S"),
                    "departure_iso": dep_dt.isoformat(),
                    "wait_minutes": (first_h * 60 - cur_mins),
                    "mode": "metro",
                    "frequency_mins": line.frequency_mins_peak if line else 8
                })
        elif cur_mins <= last_h * 60:
            for line_id in metro_station.lines:
                line = default_metro_adapter._lines_by_id.get(line_id)
                freq = line.frequency_mins_peak if (8 <= query_time_ist.hour <= 11 or 17 <= query_time_ist.hour <= 20) else line.frequency_mins_offpeak
                freq = freq or 8
                next_dep_mins = cur_mins + (freq - (cur_mins % freq))
                dep_hour = next_dep_mins // 60
                dep_min = next_dep_mins % 60
                dep_dt = query_time_ist.replace(hour=dep_hour, minute=dep_min, second=0)
                departures.append({
                    "route_short_name": line.name if line else line_id,
                    "headsign": f"Towards {line.stations[-1].replace('_', ' ').title()}" if line else "Terminal",
                    "departure_time": dep_dt.strftime("%H:%M:%S"),
                    "departure_iso": dep_dt.isoformat(),
                    "wait_minutes": (next_dep_mins - cur_mins),
                    "mode": "metro",
                    "frequency_mins": freq
                })

        if not departures:
            return {
                "error": True,
                "code": "NO_SERVICE",
                "message": f"Metro service is closed at {query_time_ist.strftime('%H:%M')} IST. Operational hours are 06:00 to 22:00.",
                "hint": "Try planning a bus trip or travel during metro operational hours (06:00 AM - 10:00 PM)."
            }

        return {
            "data": {
                "stop_id": metro_station.id,
                "stop_name": metro_station.name,
                "mode": "metro",
                "query_time_ist": query_time_ist.isoformat(),
                "departures": departures[:limit]
            },
            "source": "curated",
            "data_as_of": default_metro_adapter.data.last_verified if default_metro_adapter.data else "2026-10-11"
        }

    # 2. Bus stop departures from SQLite
    with get_db(readonly=True) as conn:
        stop = repository.get_stop_by_id(conn, clean_stop_id)
        if not stop:
            # Try fuzzy match on stop name
            cur = conn.cursor()
            cur.execute("SELECT stop_id, stop_name FROM stops WHERE lower(stop_name) LIKE ? LIMIT 1", (f"%{clean_stop_id.lower()}%",))
            matched = cur.fetchone()
            if matched:
                clean_stop_id = matched["stop_id"]
                stop = repository.get_stop_by_id(conn, clean_stop_id)
            else:
                return {
                    "error": True,
                    "code": "INVALID_INPUT",
                    "message": f"Stop '{clean_stop_id}' not found in the Pune bus or metro system.",
                    "hint": "Call find_nearby_stops first to get valid stop_id strings."
                }

        # Active service IDs for today
        active_services = repository.get_active_service_ids(conn, date_str, weekday_col)

        # Departures today
        deps = repository.get_next_departures(
            conn,
            stop_id=clean_stop_id,
            active_service_ids=active_services,
            min_dep_secs=now_secs,
            route_filter=route_filter,
            limit=limit
        )

        # After-midnight check if early morning (between 00:00 and 04:00)
        if query_time_ist.hour < 4 and len(deps) < limit:
            yesterday_dt = query_time_ist - timedelta(days=1)
            yesterday_date_str = yesterday_dt.strftime("%Y%m%d")
            yesterday_weekday_col = WEEKDAY_NAMES[yesterday_dt.weekday()]
            yesterday_active_services = repository.get_active_service_ids(conn, yesterday_date_str, yesterday_weekday_col)

            night_deps = repository.get_after_midnight_departures(
                conn,
                stop_id=clean_stop_id,
                yesterday_active_services=yesterday_active_services,
                current_time_secs=now_secs,
                route_filter=route_filter,
                limit=limit - len(deps)
            )
            deps.extend(night_deps)
            deps.sort(key=lambda x: x["departure_secs"])

        meta = repository.get_meta_info(conn)

    if not deps:
        return {
            "error": True,
            "code": "NO_SERVICE",
            "message": f"No bus departures found for stop '{stop['stop_name']}' after {query_time_ist.strftime('%H:%M')} IST.",
            "hint": "Check if a different route or an earlier/later time has scheduled service."
        }

    formatted_departures = []
    for d in deps:
        dep_secs = d["departure_secs"]
        wait_secs = dep_secs - now_secs
        dep_iso = secs_to_ist_iso(query_time_ist, dep_secs)
        formatted_departures.append({
            "route_short_name": d["route_short_name"],
            "route_long_name": d["route_long_name"],
            "headsign": d["trip_headsign"],
            "departure_time": f"{dep_secs // 3600:02d}:{(dep_secs % 3600) // 60:02d}",
            "departure_iso": dep_iso,
            "wait_minutes": max(0, round(wait_secs / 60)),
            "trip_id": d["trip_id"]
        })

    return {
        "data": {
            "stop_id": stop["stop_id"],
            "stop_name": stop["stop_name"],
            "query_time_ist": query_time_ist.isoformat(),
            "count": len(formatted_departures),
            "departures": formatted_departures
        },
        "source": "timetable",
        "data_as_of": meta.get("loaded_at", "2026-10-11")
    }


def find_routes_between(from_stop_id: str, to_stop_id: str) -> Dict[str, Any]:
    """
    Finds direct bus routes serving both stops in order.
    """
    with get_db(readonly=True) as conn:
        s1 = repository.get_stop_by_id(conn, from_stop_id)
        s2 = repository.get_stop_by_id(conn, to_stop_id)

        # Check by name if stop_id was passed as a stop name
        if not s1:
            cur = conn.cursor()
            cur.execute("SELECT stop_id, stop_name FROM stops WHERE lower(stop_name) LIKE ? LIMIT 1", (f"%{from_stop_id.lower()}%",))
            m = cur.fetchone()
            if m:
                from_stop_id = m["stop_id"]
                s1 = repository.get_stop_by_id(conn, from_stop_id)

        if not s2:
            cur = conn.cursor()
            cur.execute("SELECT stop_id, stop_name FROM stops WHERE lower(stop_name) LIKE ? LIMIT 1", (f"%{to_stop_id.lower()}%",))
            m = cur.fetchone()
            if m:
                to_stop_id = m["stop_id"]
                s2 = repository.get_stop_by_id(conn, to_stop_id)

        if not s1 or not s2:
            return {
                "error": True,
                "code": "INVALID_INPUT",
                "message": f"One or both stop IDs ('{from_stop_id}', '{to_stop_id}') could not be resolved.",
                "hint": "Use find_nearby_stops or resolve_place to identify valid stop IDs."
            }

        routes = repository.get_routes_between(conn, from_stop_id, to_stop_id)
        meta = repository.get_meta_info(conn)

    if not routes:
        return {
            "error": True,
            "code": "NO_SERVICE",
            "message": f"No direct bus route serves both '{s1['stop_name']}' and '{s2['stop_name']}' in that direction.",
            "hint": "Use plan_trip to find a route with a transfer or metro connection."
        }

    return {
        "data": {
            "from_stop": {"id": s1["stop_id"], "name": s1["stop_name"]},
            "to_stop": {"id": s2["stop_id"], "name": s2["stop_name"]},
            "direct_routes": [
                {
                    "route_id": r["route_id"],
                    "route_short_name": r["route_short_name"],
                    "route_long_name": r["route_long_name"],
                    "headsign": r["trip_headsign"]
                }
                for r in routes
            ]
        },
        "source": "timetable",
        "data_as_of": meta.get("loaded_at", "2026-10-11")
    }
