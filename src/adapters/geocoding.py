"""
src/adapters/geocoding.py

Place name geocoding adapter for Pune.
Integrates local curated places table and OpenStreetMap Nominatim with viewbox biasing.
"""

import json
import logging
import re
from typing import List, Dict, Any, Optional
import httpx
from ..config import PLACES_DATA_PATH, GEOCODER_BASE_URL
from .http_client import default_http_client

logger = logging.getLogger("pune_transit.geocoding")


def _normalize(text: str) -> str:
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(cleaned.split())


class GeocodingAdapter:
    def __init__(self, places_path: str = PLACES_DATA_PATH):
        self.places_path = places_path
        self.local_places: List[Dict[str, Any]] = []
        self._load_local_places()

    def _load_local_places(self):
        try:
            with open(self.places_path, "r", encoding="utf-8") as f:
                self.local_places = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load local places from {self.places_path}: {e}")
            self.local_places = []

    def match_local_places(self, query: str) -> List[Dict[str, Any]]:
        norm_q = _normalize(query)
        if not norm_q:
            return []

        exact_matches = []
        partial_matches = []

        for p in self.local_places:
            norm_name = _normalize(p.get("name", ""))
            aliases = [_normalize(a) for a in p.get("aliases", [])]

            # Exact name or alias match
            if norm_q == norm_name or norm_q in aliases:
                exact_matches.append(p)
                continue

            # Substring match (e.g. "hinjewadi" in "hinjewadi phase 1")
            if any(norm_q in a or a in norm_q for a in [norm_name] + aliases):
                partial_matches.append(p)

        if exact_matches:
            return exact_matches
        return partial_matches

    async def geocode(self, query: str) -> List[Dict[str, Any]]:
        """
        Resolves query to coordinate candidates.
        Checks local landmarks first, then falls back to OSM Nominatim.
        """
        # 1. Local curated match
        local_results = self.match_local_places(query)
        if local_results:
            return [
                {
                    "name": p["name"],
                    "display_name": p.get("display_name", p["name"]),
                    "lat": float(p["lat"]),
                    "lon": float(p["lon"]),
                    "area": p.get("area", "Pune"),
                    "source": "curated"
                }
                for p in local_results
            ]

        # 1b. Check Pune Metro stations directly
        from .metro_adapter import default_metro_adapter
        if default_metro_adapter.is_available:
            ms = default_metro_adapter.find_station(query)
            if ms:
                return [{
                    "name": ms.name,
                    "display_name": f"{ms.name} (Pune Metro Station)",
                    "lat": float(ms.lat),
                    "lon": float(ms.lon),
                    "area": "Pune Metro",
                    "source": "curated"
                }]

        # 2. Remote OSM Nominatim geocoding (Pune bounded)
        url = f"{GEOCODER_BASE_URL.rstrip('/')}/search"
        params = {
            "q": f"{query}, Pune, Maharashtra, India",
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": 5,
            # Pune viewbox: min_lon, max_lat, max_lon, min_lat
            "viewbox": "73.65,18.75,74.05,18.40",
            "bounded": 0
        }

        try:
            results = await default_http_client.get_json(url, params=params)
            candidates = []
            for item in results:
                try:
                    lat = float(item["lat"])
                    lon = float(item["lon"])
                except (ValueError, KeyError):
                    continue

                candidates.append({
                    "name": item.get("name") or item.get("display_name", "").split(",")[0],
                    "display_name": item.get("display_name", ""),
                    "lat": lat,
                    "lon": lon,
                    "area": item.get("address", {}).get("suburb", "Pune"),
                    "source": "geocoder"
                })
            return candidates
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            logger.warning(f"Upstream geocoding failed/timed out: {e}. Falling back to empty or partial.")
            return []
        except Exception as e:
            logger.error(f"Geocoding error: {e}")
            return []


default_geocoder = GeocodingAdapter()
