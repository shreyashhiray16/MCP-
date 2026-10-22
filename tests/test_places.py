"""
tests/test_places.py

Unit tests for places service:
- Place resolution for Pune landmarks
- Ambiguous place handling
- Save and list saved places roundtrip
"""

import pytest
from src.services.places import resolve_place, save_place, list_saved_places


@pytest.mark.asyncio
async def test_resolve_exact_place():
    res = await resolve_place("Pimpri")
    assert not res.get("error")
    data = res["data"]
    assert "lat" in data and "lon" in data
    assert 18.60 <= data["lat"] <= 18.65
    assert 73.78 <= data["lon"] <= 73.83


@pytest.mark.asyncio
async def test_resolve_hinjewadi_phase_1():
    res = await resolve_place("Hinjewadi Phase 1")
    assert not res.get("error")
    assert "Hinjewadi Phase 1" in res["data"]["name"]


@pytest.mark.asyncio
async def test_resolve_place_not_found():
    res = await resolve_place("NonExistentUnknownPlaceXYZ12345")
    assert res.get("error") is True
    assert res["code"] == "PLACE_NOT_FOUND"


@pytest.mark.asyncio
async def test_save_and_list_saved_place_roundtrip():
    # Save DY Patil Pimpri as 'college' for test_user
    test_user = "test_user_pytest"
    save_res = await save_place("college", "DY Patil Pimpri", user_id=test_user)
    assert not save_res.get("error")
    assert save_res["data"]["label"] == "college"

    # List saved places
    list_res = list_saved_places(user_id=test_user)
    assert not list_res.get("error")
    saved_items = list_res["data"]
    assert any(item["label"] == "college" for item in saved_items)

    # Resolve 'college' for test_user
    resolve_saved = await resolve_place("college", user_id=test_user)
    assert not resolve_saved.get("error")
    assert resolve_saved["data"]["label"] == "college"
