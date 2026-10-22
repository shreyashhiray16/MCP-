"""
tests/test_planner.py

Unit tests for trip planner service:
- Direct bus itineraries (Pimpri to Hinjewadi Phase 1)
- Direct metro itineraries (PCMC to Swargate)
- Multi-modal and transfer options
- Walking estimation and road comparison
"""

import pytest
from src.services.planner import plan_trip


@pytest.mark.asyncio
async def test_plan_trip_pimpri_to_hinjewadi():
    # 9:00 AM on a weekday
    res = await plan_trip(
        origin="Pimpri",
        destination="Hinjewadi Phase 1",
        depart_at="2026-10-14T09:00:00+05:30"
    )
    assert not res.get("error")
    data = res["data"]
    assert data["itineraries_count"] > 0
    itinerary = data["itineraries"][0]
    assert "total_duration_minutes" in itinerary
    assert "legs" in itinerary
    assert "road_comparison" in data
    # Road travel comparison present
    assert data["road_comparison"]["estimated_duration_minutes"] > 0


@pytest.mark.asyncio
async def test_plan_trip_pcmc_to_swargate_metro():
    res = await plan_trip(
        origin="PCMC",
        destination="Swargate",
        depart_at="2026-10-14T08:30:00+05:30",
        modes=["metro", "walk"]
    )
    assert not res.get("error")
    data = res["data"]
    assert data["itineraries_count"] > 0
    first_opt = data["itineraries"][0]
    assert any(leg.get("mode") == "metro" for leg in first_opt["legs"])


@pytest.mark.asyncio
async def test_plan_trip_walking_short_distance():
    # Short walk within Pimpri Station area
    res = await plan_trip(
        origin="Pimpri Railway Station",
        destination="Pimpri Chowk",
        depart_at="2026-10-14T10:00:00+05:30"
    )
    assert not res.get("error")
    assert res["data"]["itineraries_count"] > 0
