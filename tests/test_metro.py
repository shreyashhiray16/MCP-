"""
tests/test_metro.py

Unit tests for Pune Metro adapter and tools:
- Line retrieval
- Station retrieval
- First/last train hours
- Official fare calculation with Civil Court interchange
"""

import pytest
from src.adapters.metro_adapter import default_metro_adapter
from src.tools.transit_tools import metro_info_tool


def test_metro_adapter_loaded():
    assert default_metro_adapter.is_available is True
    assert default_metro_adapter.data is not None
    assert len(default_metro_adapter.data.lines) == 2
    assert len(default_metro_adapter.data.stations) >= 28


def test_metro_info_purple_line():
    res = metro_info_tool(line="Purple Line")
    assert not res.get("error")
    line_data = res["data"]["line"]
    assert line_data["name"] == "Purple Line"
    assert line_data["first_train"] == "06:00"
    assert line_data["last_train"] == "22:00"
    assert "pcmc" in line_data["stations"]
    assert "swargate" in line_data["stations"]


def test_metro_info_swargate_station():
    res = metro_info_tool(station="Swargate")
    assert not res.get("error")
    station_data = res["data"]["station"]
    assert station_data["name"] == "Swargate Metro Station"


def test_metro_fare_calculation_same_line():
    # PCMC to Bhosari (2 stations apart)
    fare = default_metro_adapter.calculate_fare("pcmc", "bhosari")
    assert fare == 10


def test_metro_fare_calculation_across_lines():
    # Vanaz (Aqua) to Swargate (Purple) via Civil Court interchange
    fare = default_metro_adapter.calculate_fare("vanaz", "swargate")
    assert fare is not None
    assert fare in (20, 25, 30)  # Within valid Maha-Metro fare slab


def test_metro_fare_tool_query():
    res = metro_info_tool(station="Vanaz", second_station="Ramwadi")
    assert not res.get("error")
    data = res["data"]
    assert data["fare_inr"] in (25, 30, 35)
    assert data["from_station"] == "Vanaz"
    assert data["to_station"] == "Ramwadi"
