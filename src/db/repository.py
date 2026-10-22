"""
src/db/repository.py

Data access repository for Pune Transit database.
Uses prepared statements and parameterised queries exclusively.
"""

import sqlite3
from typing import List, Dict, Any, Optional


def get_meta_info(conn: sqlite3.Connection) -> Dict[str, str]:
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM meta")
    rows = cur.fetchall()
    return {r["key"]: r["value"] for r in rows}


def get_all_stops(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    cur = conn.cursor()
    cur.execute("SELECT stop_id, stop_name, stop_lat, stop_lon FROM stops ORDER BY stop_name")
    return cur.fetchall()


def get_stop_by_id(conn: sqlite3.Connection, stop_id: str) -> Optional[Dict[str, Any]]:
    cur = conn.cursor()
    cur.execute("SELECT stop_id, stop_name, stop_lat, stop_lon FROM stops WHERE stop_id = ?", (stop_id,))
    return cur.fetchone()


def get_stops_in_bbox(conn: sqlite3.Connection, min_lat: float, max_lat: float, min_lon: float, max_lon: float) -> List[Dict[str, Any]]:
    cur = conn.cursor()
    cur.execute("""
        SELECT stop_id, stop_name, stop_lat, stop_lon
        FROM stops
        WHERE stop_lat BETWEEN ? AND ? AND stop_lon BETWEEN ? AND ?
    """, (min_lat, max_lat, min_lon, max_lon))
    return cur.fetchall()


def get_all_routes(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    cur = conn.cursor()
    cur.execute("SELECT route_id, route_short_name, route_long_name, route_type FROM routes ORDER BY route_short_name")
    return cur.fetchall()


def get_routes_for_stop(conn: sqlite3.Connection, stop_id: str) -> List[Dict[str, Any]]:
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT r.route_id, r.route_short_name, r.route_long_name, r.route_type
        FROM routes r
        JOIN trips t ON r.route_id = t.route_id
        JOIN stop_times st ON t.trip_id = st.trip_id
        WHERE st.stop_id = ?
        ORDER BY r.route_short_name
    """, (stop_id,))
    return cur.fetchall()


def get_active_service_ids(conn: sqlite3.Connection, date_str: str, weekday_col: str) -> List[str]:
    """
    Computes active GTFS service_ids for date_str ('YYYYMMDD') and weekday_col ('monday', 'tuesday', etc.).
    Takes into account calendar regular schedule and calendar_dates exceptions:
      exception_type 1 = service added
      exception_type 2 = service removed
    """
    cur = conn.cursor()
    query = f"""
        SELECT service_id
        FROM calendar
        WHERE start_date <= ? AND end_date >= ? AND {weekday_col} = 1
    """
    cur.execute(query, (date_str, date_str))
    regular_services = {r["service_id"] for r in cur.fetchall()}

    # Check exceptions
    cur.execute("""
        SELECT service_id, exception_type
        FROM calendar_dates
        WHERE date = ?
    """, (date_str,))
    exceptions = cur.fetchall()

    for exc in exceptions:
        sid = exc["service_id"]
        if exc["exception_type"] == 1:
            regular_services.add(sid)
        elif exc["exception_type"] == 2:
            regular_services.discard(sid)

    return list(regular_services)


def get_next_departures(
    conn: sqlite3.Connection,
    stop_id: str,
    active_service_ids: List[str],
    min_dep_secs: int,
    route_filter: Optional[str] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    if not active_service_ids:
        return []

    cur = conn.cursor()
    placeholders = ",".join("?" for _ in active_service_ids)
    params: List[Any] = [stop_id, min_dep_secs] + active_service_ids

    route_clause = ""
    if route_filter:
        route_clause = " AND (r.route_id = ? OR r.route_short_name = ? OR lower(r.route_short_name) = lower(?)) "
        params.extend([route_filter, route_filter, route_filter])

    params.append(limit)

    query = f"""
        SELECT
            st.trip_id,
            st.stop_sequence,
            st.departure_secs,
            t.route_id,
            t.trip_headsign,
            r.route_short_name,
            r.route_long_name
        FROM stop_times st
        JOIN trips t ON st.trip_id = t.trip_id
        JOIN routes r ON t.route_id = r.route_id
        WHERE st.stop_id = ?
          AND st.departure_secs >= ?
          AND t.service_id IN ({placeholders})
          {route_clause}
        ORDER BY st.departure_secs ASC
        LIMIT ?
    """
    cur.execute(query, params)
    return cur.fetchall()


def get_after_midnight_departures(
    conn: sqlite3.Connection,
    stop_id: str,
    yesterday_active_services: List[str],
    current_time_secs: int,
    route_filter: Optional[str] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Retrieves departures for trips that started yesterday and run past midnight (departure_secs >= 86400).
    effective_departure_secs = departure_secs - 86400 >= current_time_secs.
    """
    if not yesterday_active_services:
        return []

    cur = conn.cursor()
    placeholders = ",".join("?" for _ in yesterday_active_services)
    needed_departure_secs = 86400 + current_time_secs
    params: List[Any] = [stop_id, needed_departure_secs] + yesterday_active_services

    route_clause = ""
    if route_filter:
        route_clause = " AND (r.route_id = ? OR r.route_short_name = ?) "
        params.extend([route_filter, route_filter])

    params.append(limit)

    query = f"""
        SELECT
            st.trip_id,
            st.stop_sequence,
            (st.departure_secs - 86400) as departure_secs,
            t.route_id,
            t.trip_headsign,
            r.route_short_name,
            r.route_long_name
        FROM stop_times st
        JOIN trips t ON st.trip_id = t.trip_id
        JOIN routes r ON t.route_id = r.route_id
        WHERE st.stop_id = ?
          AND st.departure_secs >= ?
          AND t.service_id IN ({placeholders})
          {route_clause}
        ORDER BY st.departure_secs ASC
        LIMIT ?
    """
    cur.execute(query, params)
    return cur.fetchall()


def get_routes_between(conn: sqlite3.Connection, from_stop_id: str, to_stop_id: str) -> List[Dict[str, Any]]:
    """
    Finds routes that visit from_stop_id then to_stop_id with from.stop_sequence < to.stop_sequence.
    """
    cur = conn.cursor()
    query = """
        SELECT DISTINCT
            r.route_id,
            r.route_short_name,
            r.route_long_name,
            t.trip_headsign,
            st1.stop_sequence as from_sequence,
            st2.stop_sequence as to_sequence
        FROM routes r
        JOIN trips t ON r.route_id = t.route_id
        JOIN stop_times st1 ON t.trip_id = st1.trip_id
        JOIN stop_times st2 ON t.trip_id = st2.trip_id
        WHERE st1.stop_id = ?
          AND st2.stop_id = ?
          AND st1.stop_sequence < st2.stop_sequence
        ORDER BY r.route_short_name
    """
    cur.execute(query, (from_stop_id, to_stop_id))
    return cur.fetchall()


def get_direct_trips_between(
    conn: sqlite3.Connection,
    from_stop_id: str,
    to_stop_id: str,
    active_service_ids: List[str],
    min_dep_secs: int,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Finds direct trips from from_stop_id to to_stop_id scheduled on active services after min_dep_secs.
    """
    if not active_service_ids:
        return []

    cur = conn.cursor()
    placeholders = ",".join("?" for _ in active_service_ids)
    params: List[Any] = [from_stop_id, to_stop_id, min_dep_secs] + active_service_ids + [limit]

    query = f"""
        SELECT
            t.trip_id,
            r.route_id,
            r.route_short_name,
            r.route_long_name,
            t.trip_headsign,
            st1.departure_secs as origin_dep_secs,
            st2.arrival_secs as dest_arr_secs,
            (st2.arrival_secs - st1.departure_secs) as travel_time_secs,
            (st2.stop_sequence - st1.stop_sequence) as stops_count
        FROM trips t
        JOIN routes r ON t.route_id = r.route_id
        JOIN stop_times st1 ON t.trip_id = st1.trip_id
        JOIN stop_times st2 ON t.trip_id = st2.trip_id
        WHERE st1.stop_id = ?
          AND st2.stop_id = ?
          AND st1.stop_sequence < st2.stop_sequence
          AND st1.departure_secs >= ?
          AND t.service_id IN ({placeholders})
        ORDER BY st1.departure_secs ASC
        LIMIT ?
    """
    cur.execute(query, params)
    return cur.fetchall()


# User saved places
def save_user_place(conn: sqlite3.Connection, user_id: str, label: str, name: str, lat: float, lon: float):
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO saved_places (user_id, label, name, lat, lon)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, label.strip(), name.strip(), lat, lon))
    conn.commit()


def get_user_places(conn: sqlite3.Connection, user_id: str) -> List[Dict[str, Any]]:
    cur = conn.cursor()
    cur.execute("""
        SELECT label, name, lat, lon
        FROM saved_places
        WHERE user_id = ?
        ORDER BY label
    """, (user_id,))
    return cur.fetchall()


def delete_user_place(conn: sqlite3.Connection, user_id: str, label: str):
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM saved_places
        WHERE user_id = ? AND label = ?
    """, (user_id, label.strip()))
    conn.commit()
