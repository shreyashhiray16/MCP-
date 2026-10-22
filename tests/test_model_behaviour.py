"""
tests/test_model_behaviour.py

Model Behaviour Acceptance Tests:
Validates the 6 primary example conversations and 10 additional benchmark scenarios
defined in README.md and PUNE_TRANSIT_MCP_TASKS.txt Section 6.3.
"""

import json
import pytest
from src.server import create_server


@pytest.fixture
def server():
    return create_server()


@pytest.mark.asyncio
async def test_conv_1_nearby_stops_pimpri(server):
    # 'Which bus stops are near Pimpri station?' -> resolve_place, find_nearby_stops
    p = await server.call_tool("resolve_place", {"query": "Pimpri"})
    assert not p.is_error
    p_data = json.loads(p.content[0].text)["data"]

    stops_res = await server.call_tool("find_nearby_stops", {
        "lat": p_data["lat"],
        "lng": p_data["lon"],
        "radius_m": 800,
        "mode": "bus"
    })
    assert not stops_res.is_error
    stops_data = json.loads(stops_res.content[0].text)["data"]
    assert stops_data["count"] > 0
    stop_names = [s["name"] for s in stops_data["stops"]]
    assert any("Pimpri" in name for name in stop_names)


@pytest.mark.asyncio
async def test_conv_2_next_bus_shivajinagar_hinjewadi(server):
    # 'When is the next bus from the Shivajinagar stop towards Hinjewadi?'
    res = await server.call_tool("next_departures", {
        "stop_id": "STOP_SHIVAJINAGAR",
        "route": "100",
        "after": "2026-10-14T08:30:00+05:30"
    })
    assert not res.is_error
    data = json.loads(res.content[0].text)["data"]
    assert data["count"] > 0
    assert any("Hinjewadi" in d["headsign"] for d in data["departures"])


@pytest.mark.asyncio
async def test_conv_3_first_last_metro_swargate(server):
    # 'What are the first and last metro trains from Swargate?'
    res = await server.call_tool("metro_info", {"station": "Swargate"})
    assert not res.is_error
    data = json.loads(res.content[0].text)["data"]
    assert len(data["operational_details"]) > 0
    line_details = data["operational_details"][0]
    assert line_details["first_train"] == "06:00"
    assert line_details["last_train"] == "22:00"


@pytest.mark.asyncio
async def test_conv_4_save_and_plan_commute(server):
    # Save home and office
    await server.call_tool("save_place", {"label": "home", "place": "Pimpri"})
    await server.call_tool("save_place", {"label": "office", "place": "Hinjewadi Phase 1"})

    # Check saved places
    saved = await server.call_tool("list_saved_places", {})
    assert not saved.is_error
    saved_list = json.loads(saved.content[0].text)["data"]
    assert any(s["label"] == "home" for s in saved_list)
    assert any(s["label"] == "office" for s in saved_list)

    # Plan trip from home to office
    plan = await server.call_tool("plan_trip", {
        "origin": "home",
        "destination": "office",
        "depart_at": "2026-10-14T08:30:00+05:30"
    })
    assert not plan.is_error
    plan_data = json.loads(plan.content[0].text)["data"]
    assert plan_data["itineraries_count"] > 0


@pytest.mark.asyncio
async def test_conv_5_remember_office(server):
    # 'Remember Hinjewadi Phase 1 as my office'
    res = await server.call_tool("save_place", {
        "label": "office",
        "place": "Hinjewadi Phase 1"
    })
    assert not res.is_error
    payload = json.loads(res.content[0].text)
    assert payload["data"]["saved"] is True
    assert payload["data"]["label"] == "office"


@pytest.mark.asyncio
async def test_conv_6_routes_between_pimpri_and_deccan(server):
    # 'Which route stops at both Pimpri and Deccan?'
    res = await server.call_tool("find_routes_between", {
        "from_stop_id": "STOP_PIMPRI_STN",
        "to_stop_id": "STOP_DECCAN"
    })
    assert not res.is_error
    data = json.loads(res.content[0].text)["data"]
    assert len(data["direct_routes"]) > 0


@pytest.mark.asyncio
async def test_extra_fare_vanaz_to_ramwadi(server):
    # 'Fare from Vanaz to Ramwadi?'
    res = await server.call_tool("metro_info", {"station": "Vanaz", "second_station": "Ramwadi"})
    assert not res.is_error
    data = json.loads(res.content[0].text)["data"]
    assert data["fare_inr"] in (25, 30, 35)


@pytest.mark.asyncio
async def test_extra_metro_closed_at_11pm(server):
    # 'Is the metro running at 11 pm?' (Closed after 22:00)
    res = await server.call_tool("next_departures", {
        "stop_id": "swargate",
        "after": "2026-10-14T23:00:00+05:30"
    })
    payload = json.loads(res.content[0].text)
    assert payload.get("error") is True
    assert payload.get("code") == "NO_SERVICE"


@pytest.mark.asyncio
async def test_out_of_scope_mumbai_search(server):
    # Searching for Mumbai out of scope
    res = await server.call_tool("find_nearby_stops", {
        "lat": 19.0760,
        "lng": 72.8777
    })
    payload = json.loads(res.content[0].text)
    assert payload.get("error") is True
    assert payload.get("code") == "INVALID_INPUT"
