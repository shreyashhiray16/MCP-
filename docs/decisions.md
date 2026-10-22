# Pune Transit MCP: Architectural Decisions Record (ADR)

*Date: 12 October 2026*

---

## ADR 01: Language Choice - Python with Official MCP SDK
- **Decision**: Implemented using Python 3.11+ and the official Python `mcp` SDK (`mcp` 2.x).
- **Rationale**: Python provides concise async primitives, direct integration with data processing libraries, native SQLite with URI mode, and Pydantic v2 type checking for all schemas.
- **Consequences**: Standardized on `mcp.server.mcpserver.MCPServer` with Starlette ASGI support.

---

## ADR 02: Storage Layer - SQLite with Prepared Queries
- **Decision**: Use a single local SQLite database (`data/pune_transit.db`) with read-only connection pooling for transit data queries and read-write connection for `saved_places`.
- **Rationale**: Zero network overhead, microsecond query latency, ACID transactions, and zero infrastructure requirements.
- **Indexes**:
  - `idx_stops_latlon` on `stops(stop_lat, stop_lon)` for bounding box pre-filtering.
  - `idx_st_stop_dep` on `stop_times(stop_id, departure_secs)` for fast departure queries.
  - `idx_trips_route` and `idx_trips_service` on `trips`.

---

## ADR 03: Time Representation - Seconds Past Midnight in Indian Standard Time (IST)
- **Decision**: Convert all schedule times into integer seconds since midnight (0 to 86,400+), in IST (UTC+5:30).
- **Rationale**: Standard GTFS feeds allow times >= 24:00:00 for trips running past midnight. Integer arithmetic allows efficient range indexing (`departure_secs >= now_secs`) and avoids complex timestamp manipulation in hot query paths.

---

## ADR 04: Geocoding Architecture - Hybrid Local Cache + OSM Nominatim
- **Decision**: Resolve place names first against user saved places, second against curated Pune landmarks/aliases (`data/pune_places.json`) and metro station names, and third against OpenStreetMap Nominatim with Pune viewbox restriction.
- **Rationale**: 100% reliability offline for common commute queries (Hinjewadi, Pimpri, Swargate, Shivajinagar, Deccan), with zero external API calls for typical routes.

---

## ADR 05: Error Architecture - Recoverable Structured Codes
- **Decision**: Return structured JSON objects with `code`, `message`, `hint`, and `details` on transit errors (`AMBIGUOUS_PLACE`, `NO_SERVICE`, `PLACE_NOT_FOUND`, `INVALID_INPUT`).
- **Rationale**: Enables Claude to self-correct (e.g. asking the user to clarify between Hinjewadi Phase 1 vs Phase 2) rather than hallucinating plausible-sounding bus numbers or schedules.

---

## ADR 06: Remote Transport - Streamable HTTP with Constant-Time Bearer Auth
- **Decision**: Use Streamable HTTP transport mounted on `/mcp` in `src/http_server.py`, protected by Bearer token authentication verified using `secrets.compare_digest`.
- **Rationale**: Compliant with MCP remote specification, prevents timing side-channel attacks, and isolates saved places per tenant token.
