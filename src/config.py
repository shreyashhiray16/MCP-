"""
src/config.py

Configuration settings for Pune Transit MCP Server.
Loads from environment variables with sensible defaults.
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Load local .env file if present
_env_path = REPO_ROOT / ".env"
if _env_path.exists():
    try:
        for _line in _env_path.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())
    except Exception:
        pass

DB_PATH = os.environ.get("DB_PATH", str(REPO_ROOT / "data" / "pune_transit.db"))
METRO_DATA_PATH = os.environ.get("METRO_DATA_PATH", str(REPO_ROOT / "data" / "metro.json"))
PLACES_DATA_PATH = os.environ.get("PLACES_DATA_PATH", str(REPO_ROOT / "data" / "pune_places.json"))
GEOCODER_BASE_URL = os.environ.get("GEOCODER_BASE_URL", "https://nominatim.openstreetmap.org")
GEOCODER_API_KEY = os.environ.get("GEOCODER_API_KEY", "")
USER_AGENT = os.environ.get("USER_AGENT", "PuneTransitMCP/1.0 (transit-assistant@pune)")
MCP_TOKENS = os.environ.get("MCP_TOKENS", "local:demo-token-123,user1:secret-token-pune")
PORT = int(os.environ.get("PORT", "8000"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
DATA_MAX_AGE_DAYS = int(os.environ.get("DATA_MAX_AGE_DAYS", "90"))
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", os.environ.get("GOOGLE_MAP_API_KEY", "")).strip()
