"""
tests/test_departures.py

Unit tests for departures service:
- Scheduled departures for morning, afternoon, and night
- IST time handling
- Finding direct routes between stops
"""

import pytest
from src.services.departures import next_departures, find_routes_between


def test_next_departures_from_pimpri_at_9am():
    # 9:00 AM on a weekday
    res = next_departures(stop_id="STOP_PIMPRI_STN", after="2026-10-14T09:00:00+05:30", limit=5)
    assert not res.get("error")
    data = res["data"]
    assert data["stop_id"] == "STOP_PIMPRI_STN"
    assert len(data["departures"]) > 0

    first_dep = data["departures"][0]
    assert "route_short_name" in first_dep
    assert "departure_time" in first_dep
    assert "departure_iso" in first_dep
    assert first_dep["wait_minutes"] >= 0


def test_next_departures_with_route_filter():
    # Filter for Route 348 towards Hinjewadi
    res = next_departures(stop_id="STOP_PIMPRI_STN", route_filter="348", after="2026-10-14T08:30:00+05:30", limit=3)
    assert not res.get("error")
    departures = res["data"]["departures"]
    assert len(departures) > 0
    assert all(d["route_short_name"] == "348" for d in departures)


def test_find_routes_between_pimpri_and_deccan():
    res = find_routes_between(from_stop_id="STOP_PIMPRI_STN", to_stop_id="STOP_DECCAN")
    assert not res.get("error")
    routes = res["data"]["direct_routes"]
    assert len(routes) > 0
    # Route 306 or 42 connects Pimpri and Deccan
    route_numbers = [r["route_short_name"] for r in routes]
    assert "306" in route_numbers or "42" in route_numbers


def test_find_routes_between_no_direct_route():
    # Katraj to Airport has no direct bus
    res = find_routes_between(from_stop_id="STOP_KATRAJ", to_stop_id="STOP_PUNE_AIRPORT")
    assert res.get("error") is True
    assert res["code"] == "NO_SERVICE"
