"""
tests/test_stops.py

Unit tests for stops service:
- Nearby stops bounding box filtering
- Distance ordering (Haversine)
- Radius constraints
- Mode filtering (bus, metro, any)
"""

import pytest
from src.services.stops import find_nearby_stops, haversine_distance_m


def test_haversine_calculation():
    # Pimpri Station to Swargate is approximately 14-16 km
    pimpri_lat, pimpri_lon = 18.6275, 73.8012
    swargate_lat, swargate_lon = 18.5015, 73.8578
    dist = haversine_distance_m(pimpri_lat, pimpri_lon, swargate_lat, swargate_lon)
    assert 14000 <= dist <= 17000


def test_find_nearby_stops_bus_mode():
    # Near Pimpri Station
    res = find_nearby_stops(lat=18.6275, lng=73.8012, radius_m=1000, mode="bus", limit=5)
    assert not res.get("error")
    stops = res["data"]["stops"]
    assert len(stops) > 0
    # Closest stop should be Pimpri Railway Station
    assert stops[0]["id"] == "STOP_PIMPRI_STN"
    assert all(s["mode"] == "bus" for s in stops)
    # Check sorted ascending by distance
    distances = [s["distance_m"] for s in stops]
    assert distances == sorted(distances)


def test_find_nearby_stops_metro_mode():
    # Near Swargate Metro Station
    res = find_nearby_stops(lat=18.5019, lng=73.8583, radius_m=800, mode="metro", limit=5)
    assert not res.get("error")
    stops = res["data"]["stops"]
    assert len(stops) > 0
    assert stops[0]["id"] == "swargate"
    assert all(s["mode"] == "metro" for s in stops)


def test_find_nearby_stops_out_of_bounds():
    # Mumbai coordinates
    res = find_nearby_stops(lat=19.0760, lng=72.8777, radius_m=500)
    assert res.get("error") is True
    assert res["code"] == "INVALID_INPUT"
