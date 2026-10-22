"""
src/services/places.py

Places service:
- Resolves place names to coordinates using saved places, local aliases, and geocoding.
- Handles ambiguous places with AMBIGUOUS_PLACE structured errors and candidates.
- Manages user saved favourite places (home, office, college).
"""

from datetime import datetime, timezone
from typing import Dict, Any, Union, Optional
from ..db.connection import get_db
from ..db import repository
from ..adapters.geocoding import default_geocoder


async def resolve_place(query: str, user_id: str = "local") -> Dict[str, Any]:
    """
    Turns a place name like 'Pimpri', 'Shivajinagar' or 'home' into coordinates.
    Returns candidates if ambiguous.
    """
    cleaned = query.strip()
    if len(cleaned) < 2 or len(cleaned) > 100:
        return {
            "error": True,
            "code": "INVALID_INPUT",
            "message": "Query length must be between 2 and 100 characters.",
            "hint": "Provide a landmark, locality or saved place name in Pune."
        }

    # 1. Check user's saved places first
    with get_db(readonly=False) as conn:
        saved = repository.get_user_places(conn, user_id)
        for sp in saved:
            if sp["label"].lower() == cleaned.lower() or sp["name"].lower() == cleaned.lower():
                return {
                    "data": {
                        "name": sp["name"],
                        "label": sp["label"],
                        "lat": sp["lat"],
                        "lon": sp["lon"],
                        "type": "saved_place"
                    },
                    "source": "saved_places",
                    "data_as_of": datetime.now(timezone.utc).date().isoformat()
                }

    # 2. Check local curated places & geocoding
    candidates = await default_geocoder.geocode(cleaned)

    if not candidates:
        return {
            "error": True,
            "code": "PLACE_NOT_FOUND",
            "message": f"Could not find coordinates for '{cleaned}'.",
            "hint": "Try searching with a nearby major Pune landmark or area (e.g. Swargate, Shivajinagar, Hinjewadi)."
        }

    if len(candidates) == 1:
        c = candidates[0]
        return {
            "data": {
                "name": c["name"],
                "display_name": c["display_name"],
                "lat": c["lat"],
                "lon": c["lon"],
                "area": c.get("area", "")
            },
            "source": c.get("source", "curated"),
            "data_as_of": datetime.now(timezone.utc).date().isoformat()
        }

    # Multiple candidates -> AMBIGUOUS_PLACE
    # If the first candidate is an exact match for the query, prefer it directly
    for c in candidates:
        if c["name"].lower() == cleaned.lower():
            return {
                "data": {
                    "name": c["name"],
                    "display_name": c["display_name"],
                    "lat": c["lat"],
                    "lon": c["lon"],
                    "area": c.get("area", "")
                },
                "source": c.get("source", "curated"),
                "data_as_of": datetime.now(timezone.utc).date().isoformat()
            }

    return {
        "error": True,
        "code": "AMBIGUOUS_PLACE",
        "message": f"Multiple places matched '{cleaned}'.",
        "hint": "Ask the user to clarify which specific location or phase they meant.",
        "candidates": [
            {
                "name": c["name"],
                "display_name": c["display_name"],
                "lat": c["lat"],
                "lon": c["lon"],
                "area": c.get("area", "")
            }
            for c in candidates[:5]
        ]
    }


async def save_place(label: str, place: Union[str, Dict[str, Any]], user_id: str = "local") -> Dict[str, Any]:
    """
    Saves a favorite place (home, college, office) for the user.
    """
    clean_label = label.strip()
    if len(clean_label) < 1 or len(clean_label) > 40:
        return {
            "error": True,
            "code": "INVALID_INPUT",
            "message": "Place label must be between 1 and 40 characters.",
            "hint": "Use a short label such as 'home', 'office', or 'college'."
        }

    lat: float
    lon: float
    name: str

    if isinstance(place, dict) and "lat" in place and "lon" in place:
        lat = float(place["lat"])
        lon = float(place["lon"])
        name = str(place.get("name", clean_label))
    else:
        resolved = await resolve_place(str(place), user_id=user_id)
        if "error" in resolved:
            return resolved
        place_data = resolved["data"]
        lat = place_data["lat"]
        lon = place_data["lon"]
        name = place_data.get("name", str(place))

    with get_db(readonly=False) as conn:
        repository.save_user_place(conn, user_id, clean_label, name, lat, lon)

    return {
        "data": {
            "saved": True,
            "label": clean_label,
            "name": name,
            "lat": lat,
            "lon": lon
        },
        "source": "saved_places",
        "data_as_of": datetime.now(timezone.utc).date().isoformat()
    }


def list_saved_places(user_id: str = "local") -> Dict[str, Any]:
    """
    Lists all saved places for the user.
    """
    with get_db(readonly=False) as conn:
        places = repository.get_user_places(conn, user_id)

    return {
        "data": places,
        "source": "saved_places",
        "data_as_of": datetime.now(timezone.utc).date().isoformat()
    }
