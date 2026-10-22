"""
src/services/stops.py

Stops service:
- Finds transit stops (bus and metro) within a given radius using bounding box prefilter + Haversine formula.
- Supports filtering by mode ('bus', 'metro', 'any').
"""

import math
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from ..db.connection import get_db
from ..db import repository
from ..adapters.metro_adapter import default_metro_adapter


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two coordinates in meters."""
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def find_nearby_stops(
    lat: float,
    lng: float,
    radius_m: int = 500,
    mode: str = "any",
    limit: int = 10
) -> Dict[str, Any]:
    """
    Lists bus stops and metro stations near a geographic coordinate.
    """
    # Validation
    if not (18.0 <= lat <= 19.5 and 73.0 <= lng <= 75.0):
        return {
            "error": True,
            "code": "INVALID_INPUT",
            "message": f"Coordinates ({lat}, {lng}) are outside the Pune transit operational region.",
            "hint": "Provide coordinates in the Pune metropolitan area (lat ~18.5, lon ~73.8)."
        }

    radius_m = max(50, min(radius_m, 2000))
    limit = max(1, min(limit, 20))
    norm_mode = mode.lower().strip() if mode else "any"

    results: List[Dict[str, Any]] = []

    # 1. Bus stops from SQLite (if mode is bus or any)
    if norm_mode in ("bus", "any"):
        # Bounding box calculation: 1 deg lat ~ 111,000m
        lat_delta = (radius_m / 111000.0) * 1.1
        lon_delta = (radius_m / (111000.0 * math.cos(math.radians(lat)))) * 1.1

        with get_db(readonly=True) as conn:
            bus_stops = repository.get_stops_in_bbox(
                conn,
                min_lat=lat - lat_delta,
                max_lat=lat + lat_delta,
                min_lon=lng - lon_delta,
                max_lon=lng + lon_delta
            )

        for s in bus_stops:
            dist = haversine_distance_m(lat, lng, s["stop_lat"], s["stop_lon"])
            if dist <= radius_m:
                results.append({
                    "id": s["stop_id"],
                    "name": s["stop_name"],
                    "lat": s["stop_lat"],
                    "lon": s["stop_lon"],
                    "mode": "bus",
                    "distance_m": round(dist, 1)
                })

    # 2. Metro stations from Metro Adapter (if mode is metro or any)
    if norm_mode in ("metro", "any") and default_metro_adapter.is_available:
        metro_stations = default_metro_adapter.get_all_stations()
        for ms in metro_stations:
            dist = haversine_distance_m(lat, lng, ms["lat"], ms["lon"])
            if dist <= radius_m:
                results.append({
                    "id": ms["id"],
                    "name": ms["name"],
                    "lat": ms["lat"],
                    "lon": ms["lon"],
                    "mode": "metro",
                    "lines": ms["lines"],
                    "distance_m": round(dist, 1)
                })

    # Sort by distance
    results.sort(key=lambda x: x["distance_m"])
    limited_results = results[:limit]

    return {
        "data": {
            "center": {"lat": lat, "lng": lng},
            "radius_m": radius_m,
            "mode": norm_mode,
            "count": len(limited_results),
            "stops": limited_results
        },
        "source": "timetable" if norm_mode == "bus" else "curated" if norm_mode == "metro" else "hybrid",
        "data_as_of": datetime.now(timezone.utc).date().isoformat()
    }
