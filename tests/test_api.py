"""
tests/test_api.py

Unit tests for the Web Frontend REST API endpoints in http_server.py
"""

import pytest
from starlette.testclient import TestClient
from src.http_server import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_index_html_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Pune Transit" in res.text
    assert "PMPML Bus" in res.text


def test_api_resolve_endpoint(client):
    res = client.get("/api/resolve?q=Shivajinagar")
    assert res.status_code == 200
    data = res.json()
    assert data["data"]["name"] == "Shivajinagar"


def test_api_plan_endpoint(client):
    res = client.get("/api/plan?origin=Pimpri&destination=Hinjewadi+Phase+1")
    assert res.status_code == 200
    data = res.json()
    assert data["data"]["itineraries_count"] > 0


def test_api_departures_endpoint(client):
    res = client.get("/api/departures?stop_id=STOP_SHIVAJINAGAR")
    assert res.status_code == 200
    data = res.json()
    assert data["data"]["count"] > 0


def test_api_metro_endpoint(client):
    res = client.get("/api/metro")
    assert res.status_code == 200
    data = res.json()
    assert len(data["data"]["lines"]) == 2


def test_api_places_roundtrip(client):
    # Get places
    res_get = client.get("/api/places")
    assert res_get.status_code == 200

    # Save place
    res_post = client.post("/api/places", json={"label": "client_test", "place": "Katraj"})
    assert res_post.status_code == 200
    assert res_post.json()["data"]["saved"] is True


def test_api_map_config_endpoint(client):
    res = client.get("/api/map-config")
    assert res.status_code == 200
    data = res.json()
    assert "google_maps_api_key" in data
    assert "has_google_key" in data
    assert data["city"] == "Pune"
