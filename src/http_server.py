"""
src/http_server.py

Unified HTTP server for Pune Transit:
- Serves interactive Web Frontend UI at /
- Exposes REST API endpoints at /api/... for the web interface
- Exposes Streamable HTTP endpoint at /mcp for MCP remote clients (with Bearer auth)
"""

import json
import logging
import os
import secrets
from pathlib import Path
from typing import Dict, Optional, Tuple

from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, FileResponse
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Receive, Scope, Send
import uvicorn

from .server import create_server
from .config import MCP_TOKENS, PORT, GOOGLE_MAPS_API_KEY
from .services.places import resolve_place, save_place, list_saved_places
from .services.stops import find_nearby_stops
from .services.departures import next_departures
from .services.planner import plan_trip
from .adapters.metro_adapter import default_metro_adapter

logger = logging.getLogger("pune_transit.http")
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def parse_tokens(token_str: str) -> Dict[str, str]:
    token_map = {}
    for part in token_str.split(","):
        part = part.strip()
        if ":" in part:
            user_id, token = part.split(":", 1)
            token_map[token.strip()] = user_id.strip()
    return token_map


# =============================================================================
# REST API ENDPOINTS (FOR FRONTEND CLIENT)
# =============================================================================

async def api_resolve(request: Request) -> JSONResponse:
    q = request.query_params.get("q", "").strip()
    if not q:
        return JSONResponse({"error": True, "message": "Query parameter 'q' is required."}, status_code=400)
    res = await resolve_place(q)
    return JSONResponse(res)


async def api_nearby(request: Request) -> JSONResponse:
    try:
        lat = float(request.query_params.get("lat", 0))
        lng = float(request.query_params.get("lng", 0))
        radius_m = int(request.query_params.get("radius_m", 500))
        mode = request.query_params.get("mode", "any")
        limit = int(request.query_params.get("limit", 10))
    except (ValueError, TypeError):
        return JSONResponse({"error": True, "message": "Invalid numeric coordinates or radius."}, status_code=400)

    res = find_nearby_stops(lat, lng, radius_m=radius_m, mode=mode, limit=limit)
    return JSONResponse(res)


async def api_departures(request: Request) -> JSONResponse:
    stop_id = request.query_params.get("stop_id", "").strip()
    route = request.query_params.get("route")
    after = request.query_params.get("after")
    limit = int(request.query_params.get("limit", 5))

    if not stop_id:
        return JSONResponse({"error": True, "message": "Parameter 'stop_id' is required."}, status_code=400)

    res = next_departures(stop_id, route_filter=route, after=after, limit=limit)
    return JSONResponse(res)


async def api_plan(request: Request) -> JSONResponse:
    if request.method == "POST":
        try:
            body = await request.json()
            origin = body.get("origin")
            destination = body.get("destination")
            depart_at = body.get("depart_at")
            arrive_by = body.get("arrive_by")
            modes = body.get("modes")
            max_walk_m = int(body.get("max_walk_m", 1000))
        except Exception:
            return JSONResponse({"error": True, "message": "Invalid JSON body."}, status_code=400)
    else:
        origin = request.query_params.get("origin")
        destination = request.query_params.get("destination")
        depart_at = request.query_params.get("depart_at")
        arrive_by = request.query_params.get("arrive_by")
        modes_str = request.query_params.get("modes")
        modes = [m.strip() for m in modes_str.split(",")] if modes_str else None
        max_walk_m = int(request.query_params.get("max_walk_m", 1000))

    if not origin or not destination:
        return JSONResponse({"error": True, "message": "Both 'origin' and 'destination' are required."}, status_code=400)

    res = await plan_trip(
        origin=origin,
        destination=destination,
        depart_at=depart_at,
        arrive_by=arrive_by,
        modes=modes,
        max_walk_m=max_walk_m
    )
    return JSONResponse(res)


async def api_metro(request: Request) -> JSONResponse:
    s1 = request.query_params.get("station1")
    s2 = request.query_params.get("station2")
    if s1 and s2 and default_metro_adapter.is_available:
        fare = default_metro_adapter.calculate_fare(s1, s2)
        st1 = default_metro_adapter.find_station(s1)
        st2 = default_metro_adapter.find_station(s2)
        return JSONResponse({
            "from": st1.name if st1 else s1,
            "to": st2.name if st2 else s2,
            "fare_inr": fare or 15,
            "requires_interchange": "civil_court" not in (s1, s2) and set(st1.lines).isdisjoint(set(st2.lines)) if st1 and st2 else False
        })

    if not default_metro_adapter.is_available or not default_metro_adapter.data:
        return JSONResponse({"error": True, "message": "Metro data unavailable."}, status_code=503)

    return JSONResponse({"data": default_metro_adapter.data.model_dump()})


async def api_places(request: Request) -> JSONResponse:
    if request.method == "POST":
        try:
            body = await request.json()
            label = body.get("label", "").strip()
            place = body.get("place", "")
            if not label or not place:
                return JSONResponse({"error": True, "message": "Fields 'label' and 'place' are required."}, status_code=400)
            res = await save_place(label, place)
            return JSONResponse(res)
        except Exception as e:
            return JSONResponse({"error": True, "message": str(e)}, status_code=400)

    # GET
    places = list_saved_places()
    return JSONResponse(places)


async def api_map_config(request: Request) -> JSONResponse:
    global GOOGLE_MAPS_API_KEY
    if request.method == "POST":
        try:
            body = await request.json()
            new_key = body.get("google_maps_api_key", "").strip()
            GOOGLE_MAPS_API_KEY = new_key
            import src.config as conf
            conf.GOOGLE_MAPS_API_KEY = new_key
            
            # Persist to .env in REPO_ROOT
            env_file = conf.REPO_ROOT / ".env"
            lines = []
            key_written = False
            if env_file.exists():
                lines = env_file.read_text(encoding="utf-8").splitlines()
                for i, line in enumerate(lines):
                    if line.startswith("GOOGLE_MAPS_API_KEY="):
                        lines[i] = f"GOOGLE_MAPS_API_KEY={new_key}"
                        key_written = True
                        break
            if not key_written:
                lines.append(f"GOOGLE_MAPS_API_KEY={new_key}")
            env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            logger.info("Updated Google Maps API Key configuration.")
        except Exception as e:
            logger.error(f"Failed to update Google Maps API key: {e}")
            return JSONResponse({"error": True, "message": str(e)}, status_code=400)

    return JSONResponse({
        "google_maps_api_key": GOOGLE_MAPS_API_KEY,
        "has_google_key": bool(GOOGLE_MAPS_API_KEY),
        "default_engine": "google",
        "city": "Pune",
        "center": {"lat": 18.5204, "lon": 73.8567},
        "zoom": 12
    })


# =============================================================================
# MIDDLEWARE ENFORCING AUTH ON /mcp ONLY
# =============================================================================

class MCPAuthMiddleware:
    def __init__(self, app: ASGIApp, token_map: Dict[str, str]):
        self.app = app
        self.token_map = token_map

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        # Protect /mcp endpoint with Bearer auth; allow frontend & /api to be public
        if path.startswith("/mcp"):
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode("utf-8").strip()

            authenticated_user = None
            if auth_header.startswith("Bearer "):
                client_token = auth_header[7:].strip()
                for token, user_id in self.token_map.items():
                    if secrets.compare_digest(client_token, token):
                        authenticated_user = user_id
                        break

            if not authenticated_user:
                resp = JSONResponse(
                    {
                        "error": True,
                        "code": "UNAUTHORIZED",
                        "message": "Missing or invalid Bearer authentication token for MCP endpoint.",
                        "hint": "Provide a valid Authorization: Bearer <token> header."
                    },
                    status_code=401
                )
                await resp(scope, receive, send)
                return

        await self.app(scope, receive, send)


def create_app() -> Starlette:
    token_map = parse_tokens(MCP_TOKENS)
    server = create_server()

    # Get MCP Starlette app
    mcp_starlette = server.streamable_http_app(streamable_http_path="/mcp")

    # Define REST API routes
    api_routes = [
        Route("/api/resolve", api_resolve, methods=["GET"]),
        Route("/api/nearby", api_nearby, methods=["GET"]),
        Route("/api/departures", api_departures, methods=["GET"]),
        Route("/api/plan", api_plan, methods=["GET", "POST"]),
        Route("/api/metro", api_metro, methods=["GET"]),
        Route("/api/places", api_places, methods=["GET", "POST"]),
        Route("/api/map-config", api_map_config, methods=["GET", "POST"]),
        Route("/health", lambda r: JSONResponse({"status": "ok", "service": "pune-transit-mcp"}), methods=["GET"]),
    ]

    # Combine routes with MCP Mount and Static Files Mount
    app = Starlette(
        routes=[
            *api_routes,
            Mount("/mcp", app=mcp_starlette),
            Mount("/", app=StaticFiles(directory=str(FRONTEND_DIR), html=True)),
        ]
    )

    # Wrap with MCP Auth & CORS
    auth_wrapped_app = MCPAuthMiddleware(app, token_map=token_map)
    cors_wrapped_app = CORSMiddleware(
        app=auth_wrapped_app,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"]
    )

    return cors_wrapped_app


def main():
    port = PORT
    logger.info(f"Starting Pune Transit Server on port {port} (Web UI: http://localhost:{port}/)...")
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
